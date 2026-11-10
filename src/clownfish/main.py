import codecs
import dataclasses
import fcntl
import os
import pty
import re
import signal
import struct
import sys
import termios
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from collections import deque
from typing import List, Optional, Set, Tuple


DEFAULT_FG = (229, 229, 229)
DEFAULT_BG = (20, 20, 25)
WORD_DELIMITERS = set(" \t\n\r()[]{}\"'`:;,=")


# =====================================================================
# 1. DATA MODELS & SELECTION
# =====================================================================

@dataclasses.dataclass(slots=True)
class Style:
    fg: Tuple[int, int, int] = DEFAULT_FG
    bg: Tuple[int, int, int] = DEFAULT_BG
    bold: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False

    def copy(self) -> "Style":
        return Style(
            self.fg, self.bg, self.bold, self.italic, self.underline, self.reverse
        )


@dataclasses.dataclass(slots=True)
class Cell:
    char: str = " "
    style: Style = dataclasses.field(default_factory=Style)
    url: Optional[str] = None  # OSC 8 Hyperlink target


@dataclasses.dataclass
class Selection:
    active: bool = False
    start_col: int = 0
    start_row: int = 0
    end_col: int = 0
    end_row: int = 0

    def is_empty(self) -> bool:
        return not self.active or (
            self.start_col == self.end_col and self.start_row == self.end_row
        )

    def normalized(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        p1 = (self.start_col, self.start_row)
        p2 = (self.end_col, self.end_row)
        if (p1[1], p1[0]) <= (p2[1], p2[0]):
            return p1, p2
        return p2, p1


# =====================================================================
# 2. SCREEN BUFFER
# =====================================================================

class ScreenBuffer:
    ANSI_16 = [
        (20, 20, 25),     (205, 49, 49),    (13, 188, 121),   (229, 229, 16),
        (36, 114, 200),   (188, 63, 188),   (17, 168, 205),   (229, 229, 229),
        (102, 102, 102),  (241, 76, 76),    (35, 209, 139),   (245, 245, 67),
        (59, 142, 234),   (214, 112, 214),  (41, 184, 219),   (255, 255, 255),
    ]

    def __init__(self, cols: int = 80, rows: int = 24, max_scrollback: int = 10_000):
        self.cols = cols
        self.rows = rows
        self.cursor_x = 0
        self.cursor_y = 0
        self.cursor_visible = True
        self.saved_cursor = (0, 0)
        self.current_style = Style()
        self.current_url: Optional[str] = None
        self.scroll_top = 0
        self.scroll_bottom = rows - 1
        self.dirty_lines: Set[int] = set(range(rows))

        self.primary_grid: List[List[Cell]] = [self._blank_row() for _ in range(rows)]
        self.scrollback: deque[List[Cell]] = deque(maxlen=max_scrollback)
        self.scroll_offset = 0

        self.alt_grid: List[List[Cell]] = [self._blank_row() for _ in range(rows)]
        self.is_alt_screen = False
        self._primary_saved_cursor = (0, 0)
        self._primary_saved_style = Style()

        self.grid = self.primary_grid

    def _blank_row(self) -> List[Cell]:
        return [
            Cell(style=self.current_style.copy(), url=self.current_url)
            for _ in range(self.cols)
        ]

    def mark_all_dirty(self):
        self.dirty_lines.update(range(self.rows))

    def enter_alt_screen(self):
        if self.is_alt_screen:
            return
        self.is_alt_screen = True
        self._primary_saved_cursor = (self.cursor_x, self.cursor_y)
        self._primary_saved_style = self.current_style.copy()
        self.grid = self.alt_grid
        self.scroll_offset = 0
        self.cursor_x = 0
        self.cursor_y = 0
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.erase_in_display(2)
        self.mark_all_dirty()

    def exit_alt_screen(self):
        if not self.is_alt_screen:
            return
        self.is_alt_screen = False
        self.grid = self.primary_grid
        self.cursor_x, self.cursor_y = self._primary_saved_cursor
        self.current_style = self._primary_saved_style.copy()
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.mark_all_dirty()

    def scroll_up(self, count: int = 1):
        for _ in range(count):
            popped = self.grid.pop(self.scroll_top)
            if not self.is_alt_screen and self.scroll_top == 0 and self.scroll_bottom == self.rows - 1:
                self.scrollback.append(popped)
            self.grid.insert(self.scroll_bottom, self._blank_row())

        if not self.is_alt_screen and self.scroll_offset > 0:
            self.scroll_offset = min(len(self.scrollback), self.scroll_offset + count)

        self.mark_all_dirty()

    def scroll_down(self, count: int = 1):
        for _ in range(count):
            del self.grid[self.scroll_bottom]
            self.grid.insert(self.scroll_top, self._blank_row())
        self.mark_all_dirty()

    def get_visible_row(self, r: int) -> List[Cell]:
        if self.is_alt_screen or self.scroll_offset == 0:
            return self.grid[r]

        history_len = len(self.scrollback)
        view_start = history_len - self.scroll_offset
        target_idx = view_start + r

        if target_idx < 0:
            return self._blank_row()
        elif target_idx < history_len:
            return self.scrollback[target_idx]
        else:
            grid_idx = target_idx - history_len
            if grid_idx < self.rows:
                return self.grid[grid_idx]
            return self._blank_row()

    def scroll_view(self, delta: int):
        if self.is_alt_screen:
            return
        old = self.scroll_offset
        self.scroll_offset = max(0, min(len(self.scrollback), self.scroll_offset + delta))
        if self.scroll_offset != old:
            self.mark_all_dirty()

    def reset_view(self):
        if self.scroll_offset != 0:
            self.scroll_offset = 0
            self.mark_all_dirty()

    def move_cursor(self, row: int, col: int):
        self.cursor_y = max(0, min(self.rows - 1, row))
        self.cursor_x = max(0, min(self.cols - 1, col))

    def save_cursor(self):
        self.saved_cursor = (self.cursor_x, self.cursor_y)

    def restore_cursor(self):
        self.cursor_x, self.cursor_y = self.saved_cursor

    def put_char(self, char: str):
        if self.cursor_x >= self.cols:
            self.cursor_x = 0
            self.cursor_y += 1
        if self.cursor_y > self.scroll_bottom:
            self.scroll_up(1)
            self.cursor_y = self.scroll_bottom

        self.grid[self.cursor_y][self.cursor_x] = Cell(
            char=char,
            style=self.current_style.copy(),
            url=self.current_url
        )
        self.dirty_lines.add(self.cursor_y)
        self.cursor_x += 1

    def erase_in_display(self, mode: int = 0):
        if mode == 0:
            self.erase_in_line(0)
            for y in range(self.cursor_y + 1, self.rows):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
        elif mode == 1:
            for y in range(0, self.cursor_y):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
            self.erase_in_line(1)
        elif mode in (2, 3):
            self.grid = [self._blank_row() for _ in range(self.rows)]
            if self.is_alt_screen:
                self.alt_grid = self.grid
            else:
                self.primary_grid = self.grid
            self.mark_all_dirty()

    def erase_in_line(self, mode: int = 0):
        y = self.cursor_y
        if mode == 0:
            for x in range(self.cursor_x, self.cols):
                self.grid[y][x] = Cell(style=self.current_style.copy())
        elif mode == 1:
            for x in range(0, min(self.cursor_x + 1, self.cols)):
                self.grid[y][x] = Cell(style=self.current_style.copy())
        elif mode == 2:
            self.grid[y] = self._blank_row()
        self.dirty_lines.add(y)

    def insert_chars(self, count: int):
        y, x = self.cursor_y, self.cursor_x
        for _ in range(count):
            self.grid[y].insert(x, Cell(style=self.current_style.copy(), url=self.current_url))
            self.grid[y].pop()
        self.dirty_lines.add(y)

    def delete_chars(self, count: int):
        y, x = self.cursor_y, self.cursor_x
        for _ in range(count):
            if x < len(self.grid[y]):
                self.grid[y].pop(x)
                self.grid[y].append(Cell(style=self.current_style.copy(), url=self.current_url))
        self.dirty_lines.add(y)

    def resize(self, new_cols: int, new_rows: int):
        if new_cols == self.cols and new_rows == self.rows:
            return

        def _resize_target(grid, push_to_history=False):
            if new_rows < self.rows:
                excess = self.rows - new_rows
                for _ in range(excess):
                    if grid:
                        popped = grid.pop(0)
                        if push_to_history:
                            self.scrollback.append(popped)
            elif new_rows > self.rows:
                needed = new_rows - self.rows
                for _ in range(needed):
                    if push_to_history and self.scrollback:
                        grid.insert(0, self.scrollback.pop())
                    else:
                        grid.append([Cell(style=self.current_style.copy()) for _ in range(new_cols)])

            for r in range(len(grid)):
                curr_len = len(grid[r])
                if new_cols > curr_len:
                    grid[r].extend([Cell(style=self.current_style.copy()) for _ in range(new_cols - curr_len)])
                elif new_cols < curr_len:
                    grid[r] = grid[r][:new_cols]

        _resize_target(self.primary_grid, push_to_history=True)
        _resize_target(self.alt_grid, push_to_history=False)

        self.cols = new_cols
        self.rows = new_rows
        self.scroll_top = 0
        self.scroll_bottom = new_rows - 1
        self.cursor_x = max(0, min(self.cols - 1, self.cursor_x))
        self.cursor_y = max(0, min(self.rows - 1, self.cursor_y))
        self.mark_all_dirty()

    def handle_sgr(self, params: List[int]):
        if not params:
            params = [0]
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self.current_style = Style()
            elif p == 1:
                self.current_style.bold = True
            elif p == 3:
                self.current_style.italic = True
            elif p == 4:
                self.current_style.underline = True
            elif p == 7:
                self.current_style.reverse = True
            elif p == 22:
                self.current_style.bold = False
            elif p == 23:
                self.current_style.italic = False
            elif p == 24:
                self.current_style.underline = False
            elif p == 27:
                self.current_style.reverse = False
            elif 30 <= p <= 37:
                self.current_style.fg = self.ANSI_16[p - 30]
            elif p == 39:
                self.current_style.fg = DEFAULT_FG
            elif 40 <= p <= 47:
                self.current_style.bg = self.ANSI_16[p - 40]
            elif p == 49:
                self.current_style.bg = DEFAULT_BG
            elif 90 <= p <= 97:
                self.current_style.fg = self.ANSI_16[p - 90 + 8]
            elif 100 <= p <= 107:
                self.current_style.bg = self.ANSI_16[p - 100 + 8]
            elif p in (38, 48):
                color, consumed = self._parse_extended_color(params[i + 1 :])
                if color:
                    if p == 38:
                        self.current_style.fg = color
                    else:
                        self.current_style.bg = color
                i += consumed
            i += 1

    def _parse_extended_color(self, sub: List[int]):
        if not sub:
            return None, 0
        if sub[0] == 2 and len(sub) >= 4:
            return (sub[1], sub[2], sub[3]), 4
        elif sub[0] == 5 and len(sub) >= 2:
            return self._index_to_rgb(sub[1]), 2
        return None, 0

    @classmethod
    def _index_to_rgb(cls, idx: int) -> Tuple[int, int, int]:
        if idx < 16:
            return cls.ANSI_16[idx]
        elif idx <= 231:
            idx -= 16
            return ((idx // 36) % 6 * 51, (idx // 6) % 6 * 51, (idx % 6) * 51)
        elif idx <= 255:
            g = (idx - 232) * 10 + 8
            return (g, g, g)
        return DEFAULT_FG


# =====================================================================
# 3. VT100 / OSC / SGR PARSER
# =====================================================================

class VT100Parser:
    STATE_GROUND = 0
    STATE_ESCAPE = 1
    STATE_CSI = 2
    STATE_OSC = 3

    def __init__(self, screen: ScreenBuffer):
        self.screen = screen
        self.state = self.STATE_GROUND
        self.params: List[int] = []
        self.current_param = ""
        self.private_mode = False
        self.osc_payload = ""

        # Terminal Flags
        self.application_cursor_keys = False
        self.bracketed_paste_mode = False
        self.mouse_tracking = False     # ?1000h (Normal tracking)
        self.sgr_mouse_mode = False      # ?1006h (SGR decimal format)

    def feed(self, text: str):
        for char in text:
            if self.state == self.STATE_GROUND:
                self._handle_ground(char)
            elif self.state == self.STATE_ESCAPE:
                self._handle_escape(char)
            elif self.state == self.STATE_CSI:
                self._handle_csi(char)
            elif self.state == self.STATE_OSC:
                self._handle_osc(char)

    def _handle_ground(self, char: str):
        if char == "\x1b":
            self.state = self.STATE_ESCAPE
        elif char == "\r":
            self.screen.cursor_x = 0
        elif char in ("\n", "\x0b", "\x0c"):
            self.screen.cursor_y += 1
            if self.screen.cursor_y > self.screen.scroll_bottom:
                self.screen.scroll_up(1)
                self.screen.cursor_y = self.screen.scroll_bottom
        elif char == "\b":
            self.screen.cursor_x = max(0, self.screen.cursor_x - 1)
        elif char == "\t":
            self.screen.cursor_x = min(self.screen.cols - 1, (self.screen.cursor_x + 8) & ~7)
        elif ord(char) >= 32:
            self.screen.put_char(char)

    def _handle_escape(self, char: str):
        if char == "[":
            self.state = self.STATE_CSI
            self.params = []
            self.current_param = ""
            self.private_mode = False
        elif char == "]":
            self.state = self.STATE_OSC
            self.osc_payload = ""
        elif char == "7":
            self.screen.save_cursor()
            self.state = self.STATE_GROUND
        elif char == "8":
            self.screen.restore_cursor()
            self.state = self.STATE_GROUND
        elif char == "M":
            if self.screen.cursor_y == self.screen.scroll_top:
                self.screen.scroll_down(1)
            else:
                self.screen.cursor_y = max(0, self.screen.cursor_y - 1)
            self.state = self.STATE_GROUND
        elif char == "c":
            self.screen.erase_in_display(2)
            self.screen.move_cursor(0, 0)
            self.state = self.STATE_GROUND
        else:
            self.state = self.STATE_GROUND

    def _handle_csi(self, char: str):
        if char == "?":
            self.private_mode = True
        elif "0" <= char <= "9":
            self.current_param += char
        elif char == ";":
            self.params.append(int(self.current_param) if self.current_param else 0)
            self.current_param = ""
        elif 0x40 <= ord(char) <= 0x7E:
            if self.current_param:
                self.params.append(int(self.current_param))
            self._dispatch_csi(char)
            self.state = self.STATE_GROUND

    def _dispatch_csi(self, final: str):
        p = self.params
        val1 = p[0] if (p and p[0] > 0) else 1

        if self.private_mode:
            enable = (final == "h")
            for mode in (p if p else [0]):
                if mode == 1:
                    self.application_cursor_keys = enable
                elif mode == 25:
                    self.screen.cursor_visible = enable
                elif mode in (47, 1047, 1049):
                    if enable:
                        self.screen.enter_alt_screen()
                    else:
                        self.screen.exit_alt_screen()
                elif mode == 2004:
                    self.bracketed_paste_mode = enable
                elif mode == 1000:
                    self.mouse_tracking = enable
                elif mode == 1006:
                    self.sgr_mouse_mode = enable
            return

        if final == "A":
            self.screen.cursor_y = max(0, self.screen.cursor_y - val1)
        elif final == "B":
            self.screen.cursor_y = min(self.screen.rows - 1, self.screen.cursor_y + val1)
        elif final == "C":
            self.screen.cursor_x = min(self.screen.cols - 1, self.screen.cursor_x + val1)
        elif final == "D":
            self.screen.cursor_x = max(0, self.screen.cursor_x - val1)
        elif final == "G":
            self.screen.cursor_x = min(self.screen.cols - 1, max(0, val1 - 1))
        elif final == "d":
            self.screen.cursor_y = min(self.screen.rows - 1, max(0, val1 - 1))
        elif final in ("H", "f"):
            row = (p[0] - 1) if (len(p) > 0 and p[0] > 0) else 0
            col = (p[1] - 1) if (len(p) > 1 and p[1] > 0) else 0
            self.screen.move_cursor(row, col)
        elif final == "J":
            self.screen.erase_in_display(p[0] if p else 0)
        elif final == "K":
            self.screen.erase_in_line(p[0] if p else 0)
        elif final == "@":
            self.screen.insert_chars(val1)
        elif final == "P":
            self.screen.delete_chars(val1)
        elif final == "m":
            self.screen.handle_sgr(p)
        elif final == "r":
            top = (p[0] - 1) if (len(p) > 0 and p[0] > 0) else 0
            bottom = (p[1] - 1) if (len(p) > 1 and p[1] > 0) else (self.screen.rows - 1)
            if 0 <= top < bottom < self.screen.rows:
                self.screen.scroll_top = top
                self.screen.scroll_bottom = bottom
                self.screen.move_cursor(0, 0)

    def _handle_osc(self, char: str):
        if char in ("\x07", "\x9c"):
            self._dispatch_osc(self.osc_payload)
            self.state = self.STATE_GROUND
        elif char == "\\" and self.osc_payload.endswith("\x1b"):
            self._dispatch_osc(self.osc_payload[:-1])
            self.state = self.STATE_GROUND
        else:
            self.osc_payload += char

    def _dispatch_osc(self, payload: str):
        # OSC 8 Hyperlink: 8;params;URL
        if payload.startswith("8;"):
            parts = payload.split(";", 2)
            if len(parts) >= 3:
                url = parts[2]
                self.screen.current_url = url if url else None


# =====================================================================
# 4. TKINTER TERMINAL APPLICATION
# =====================================================================

class TkTerminalApp:
    def __init__(self, root: tk.Tk, cols: int = 80, rows: int = 24):
        self.root = root
        self.cols = cols
        self.rows = rows
        self._resize_job: Optional[str] = None
        self.selection = Selection()

        self.screen = ScreenBuffer(cols=cols, rows=rows, max_scrollback=10_000)
        self.parser = VT100Parser(self.screen)
        self.utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        font_family = "Menlo" if sys.platform == "darwin" else "Monospace"
        self.fonts = {
            (False, False): tkfont.Font(family=font_family, size=13),
            (True, False): tkfont.Font(family=font_family, size=13, weight="bold"),
            (False, True): tkfont.Font(family=font_family, size=13, slant="italic"),
            (True, True): tkfont.Font(family=font_family, size=13, weight="bold", slant="italic"),
        }
        self.cell_w = self.fonts[(False, False)].measure("M")
        self.cell_h = self.fonts[(False, False)].metrics("linespace")

        self.canvas = tk.Canvas(
            root,
            width=self.cols * self.cell_w,
            height=self.rows * self.cell_h,
            bg=self._rgb_to_hex(DEFAULT_BG),
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Mouse & Pointer Interactions
        self.canvas.bind("<Button-1>", self._on_button_1_press)
        self.canvas.bind("<B1-Motion>", self._on_button_1_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_1_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Triple-Button-1>", self._on_triple_click)
        self.canvas.bind("<Motion>", self._on_pointer_motion)

        # Mouse Wheel & Buttons
        self.canvas.bind("<Button-4>", lambda e: self._on_mouse_scroll(-3, e))
        self.canvas.bind("<Button-5>", lambda e: self._on_mouse_scroll(3, e))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Keyboard & Clipboard Shortcuts
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.focus_set()
        self.root.bind("<Configure>", self._on_window_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Copy & Paste
        self.root.bind("<Control-Shift-C>", self._copy_selection_to_clipboard)
        self.root.bind("<Control-Shift-c>", self._copy_selection_to_clipboard)
        self.root.bind("<Control-Shift-V>", self._paste_from_clipboard)
        self.root.bind("<Control-Shift-v>", self._paste_from_clipboard)
        if sys.platform == "darwin":
            self.root.bind("<Command-c>", self._copy_selection_to_clipboard)
            self.root.bind("<Command-v>", self._paste_from_clipboard)
        self.canvas.bind("<Button-2>", lambda e: self._paste_from_clipboard())

        # Spawn PTY
        self.pid, self.master_fd = pty.fork()
        if self.pid == 0:
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            shell = os.environ.get("SHELL", "/bin/sh")
            os.execvp(shell, [shell])

        os.set_blocking(self.master_fd, False)
        self._set_pty_size(self.rows, self.cols)
        self.root.tk.createfilehandler(self.master_fd, tk.READABLE, self._on_pty_read)

        self._render_tick()

    @staticmethod
    def _rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _set_pty_size(self, rows: int, cols: int):
        winsize = struct.pack("HHHH", rows, cols, cols * self.cell_w, rows * self.cell_h)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def _pixel_to_cell(self, x: int, y: int) -> Tuple[int, int]:
        col = max(0, min(self.cols - 1, x // self.cell_w))
        row = max(0, min(self.rows - 1, y // self.cell_h))
        return col, row

    # --- Mouse Reporting (?1000h / ?1006h) ---

    def _send_sgr_mouse(self, button: int, col: int, row: int, release: bool = False):
        if not self.parser.mouse_tracking:
            return
        # Terminal coordinates are 1-indexed
        final = "m" if release else "M"
        if self.parser.sgr_mouse_mode:
            packet = f"\x1b[<{button};{col + 1};{row + 1}{final}".encode("utf-8")
        else:
            # Fallback classic X10 3-byte encoding
            cb = 32 + (button if not release else 3)
            cx = 32 + min(223, col + 1)
            cy = 32 + min(223, row + 1)
            packet = bytes([0x1b, ord("["), ord("M"), cb, cx, cy])
        try:
            os.write(self.master_fd, packet)
        except OSError:
            pass

    # --- Mouse Event Handlers ---

    def _on_button_1_press(self, event: tk.Event):
        col, row = self._pixel_to_cell(event.x, event.y)
        if self.parser.mouse_tracking:
            self._send_sgr_mouse(0, col, row, release=False)
            return

        # OSC 8 Hyperlink click handling
        cell = self.screen.get_visible_row(row)[col]
        if cell.url and (event.state & 0x4 or sys.platform == "darwin" and event.state & 0x8):
            # Ctrl+Click (or Cmd+Click on macOS) opens link
            webbrowser.open(cell.url)
            return

        self.selection = Selection(
            active=True,
            start_col=col,
            start_row=row,
            end_col=col,
            end_row=row
        )
        self._draw_selection_overlay()
        self.canvas.focus_set()

    def _on_button_1_motion(self, event: tk.Event):
        col, row = self._pixel_to_cell(event.x, event.y)
        if self.parser.mouse_tracking:
            return
        if not self.selection.active:
            return
        self.selection.end_col = col
        self.selection.end_row = row
        self._draw_selection_overlay()

    def _on_button_1_release(self, event: tk.Event):
        col, row = self._pixel_to_cell(event.x, event.y)
        if self.parser.mouse_tracking:
            self._send_sgr_mouse(0, col, row, release=True)
            return
        if self.selection.is_empty():
            self.selection.active = False
            self.canvas.delete("selection_box")

    def _on_double_click(self, event: tk.Event):
        if self.parser.mouse_tracking:
            return
        col, row = self._pixel_to_cell(event.x, event.y)
        row_cells = self.screen.get_visible_row(row)

        # Expand left
        start_col = col
        while start_col > 0 and row_cells[start_col - 1].char not in WORD_DELIMITERS:
            start_col -= 1

        # Expand right
        end_col = col
        while end_col < self.cols - 1 and row_cells[end_col + 1].char not in WORD_DELIMITERS:
            end_col += 1

        self.selection = Selection(
            active=True,
            start_col=start_col,
            start_row=row,
            end_col=end_col,
            end_row=row
        )
        self._draw_selection_overlay()

    def _on_triple_click(self, event: tk.Event):
        if self.parser.mouse_tracking:
            return
        col, row = self._pixel_to_cell(event.x, event.y)
        self.selection = Selection(
            active=True,
            start_col=0,
            start_row=row,
            end_col=self.cols - 1,
            end_row=row
        )
        self._draw_selection_overlay()

    def _on_pointer_motion(self, event: tk.Event):
        # Update cursor hover shape for OSC 8 hyperlinks
        col, row = self._pixel_to_cell(event.x, event.y)
        cell = self.screen.get_visible_row(row)[col]
        if cell.url:
            self.canvas.config(cursor="hand2")
        else:
            self.canvas.config(cursor="xterm")

    def _on_mousewheel(self, event: tk.Event):
        delta = -event.delta if sys.platform == "darwin" else (-1 if event.delta > 0 else 1) * 3
        self._on_mouse_scroll(delta, event)

    def _on_mouse_scroll(self, delta: int, event: Optional[tk.Event] = None):
        if self.parser.mouse_tracking and event is not None:
            col, row = self._pixel_to_cell(event.x, event.y)
            # Wheel Up: button 64, Wheel Down: button 65
            btn = 64 if delta < 0 else 65
            self._send_sgr_mouse(btn, col, row, release=False)
            return

        self.canvas.delete("selection_box")
        self.selection.active = False
        self.screen.scroll_view(-delta)

    # --- Clipboard & Keystrokes ---

    def _copy_selection_to_clipboard(self, event: Optional[tk.Event] = None) -> str:
        if self.selection.is_empty():
            return "break"

        (c1, r1), (c2, r2) = self.selection.normalized()
        lines: List[str] = []

        for r in range(r1, r2 + 1):
            row_cells = self.screen.get_visible_row(r)
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else self.cols - 1
            line_text = "".join(cell.char for cell in row_cells[sc : ec + 1])
            lines.append(line_text.rstrip())

        selected_text = "\n".join(lines)
        if selected_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
            self.root.update()

        return "break"

    def _paste_from_clipboard(self, event: Optional[tk.Event] = None) -> str:
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            return "break"

        if not clipboard_text:
            return "break"

        self.screen.reset_view()
        payload = clipboard_text.replace("\r\n", "\r").replace("\n", "\r")
        raw_bytes = payload.encode("utf-8")

        if self.parser.bracketed_paste_mode:
            formatted_stream = b"\x1b[200~" + raw_bytes + b"\x1b[201~"
        else:
            formatted_stream = raw_bytes

        try:
            os.write(self.master_fd, formatted_stream)
        except OSError:
            pass

        return "break"

    def _on_key_press(self, event: tk.Event) -> str:
        self.screen.reset_view()

        if event.keysym == "Escape" and self.selection.active:
            self.selection.active = False
            self.canvas.delete("selection_box")
            return "break"

        if event.keysym == "Prior" and (event.state & 0x1):
            self.screen.scroll_view(self.rows // 2)
            return "break"
        elif event.keysym == "Next" and (event.state & 0x1):
            self.screen.scroll_view(-(self.rows // 2))
            return "break"

        app_cursor = self.parser.application_cursor_keys
        arrow_prefix = b"\x1bO" if app_cursor else b"\x1b["

        arrow_map = {
            "Up": arrow_prefix + b"A",
            "Down": arrow_prefix + b"B",
            "Right": arrow_prefix + b"C",
            "Left": arrow_prefix + b"D",
            "Home": arrow_prefix + b"H",
            "End": arrow_prefix + b"F",
        }

        keymap = {
            "Return": b"\r",
            "BackSpace": b"\x7f",
            "Tab": b"\t",
            "Escape": b"\x1b",
            "Delete": b"\x1b[3~",
            "Prior": b"\x1b[5~",
            "Next": b"\x1b[6~",
        }

        if event.keysym in arrow_map:
            os.write(self.master_fd, arrow_map[event.keysym])
        elif event.keysym in keymap:
            os.write(self.master_fd, keymap[event.keysym])
        elif (event.state & 0x4) and event.keysym.isalpha() and len(event.keysym) == 1:
            ctrl_byte = bytes([ord(event.keysym.lower()) - 96])
            os.write(self.master_fd, ctrl_byte)
        elif event.char:
            os.write(self.master_fd, event.char.encode("utf-8"))

        return "break"

    # --- Window Resize & Background Read ---

    def _on_window_configure(self, event: tk.Event):
        if event.widget != self.root:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(50, self._apply_resize, event.width, event.height)

    def _apply_resize(self, width: int, height: int):
        self._resize_job = None
        new_cols = max(10, width // self.cell_w)
        new_rows = max(5, height // self.cell_h)

        if new_cols == self.cols and new_rows == self.rows:
            return

        self.cols = new_cols
        self.rows = new_rows
        self.canvas.delete("selection_box")
        self.selection.active = False
        self.screen.resize(new_cols, new_rows)
        self._set_pty_size(new_rows, new_cols)
        self.canvas.delete("all")
        self.screen.mark_all_dirty()

    def _on_pty_read(self, fd: int, _mask: int):
        try:
            raw_bytes = os.read(fd, 65536)
            if not raw_bytes:
                self._on_close()
                return
            text = self.utf8_decoder.decode(raw_bytes, final=False)
            self.parser.feed(text)
        except BlockingIOError:
            pass
        except OSError:
            self._on_close()

    # --- Render Pipeline ---

    def _render_tick(self):
        if self.screen.dirty_lines:
            for r in list(self.screen.dirty_lines):
                self._render_row(r)
            self.screen.dirty_lines.clear()

        self.canvas.delete("cursor")
        if self.screen.cursor_visible and self.screen.scroll_offset == 0:
            cx = self.screen.cursor_x * self.cell_w
            cy = self.screen.cursor_y * self.cell_h
            self.canvas.create_rectangle(
                cx, cy, cx + self.cell_w, cy + self.cell_h,
                fill="#e5e5e5", outline="", stipple="gray50", tags="cursor"
            )

        self.root.after(16, self._render_tick)

    def _draw_selection_overlay(self):
        self.canvas.delete("selection_box")
        if self.selection.is_empty():
            return

        (c1, r1), (c2, r2) = self.selection.normalized()
        for r in range(r1, r2 + 1):
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else self.cols - 1
            x1 = sc * self.cell_w
            y1 = r * self.cell_h
            x2 = (ec + 1) * self.cell_w
            y2 = (r + 1) * self.cell_h

            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill="#4a90e2", outline="", stipple="gray50", tags="selection_box"
            )

        self.canvas.tag_raise("cursor")

    def _render_row(self, r: int):
        tag = f"row_{r}"
        self.canvas.delete(tag)
        y = r * self.cell_h
        row_cells = self.screen.get_visible_row(r)

        col = 0
        while col < self.cols:
            cell = row_cells[col]
            st = cell.style
            url = cell.url
            fg = st.bg if st.reverse else st.fg
            bg = st.fg if st.reverse else st.bg

            span_chars = [cell.char]
            next_col = col + 1
            while next_col < self.cols:
                nc = row_cells[next_col]
                if nc.style == st and nc.url == url:
                    span_chars.append(nc.char)
                    next_col += 1
                else:
                    break

            x1 = col * self.cell_w
            x2 = next_col * self.cell_w
            text_str = "".join(span_chars)

            if bg != DEFAULT_BG:
                self.canvas.create_rectangle(
                    x1, y, x2, y + self.cell_h,
                    fill=self._rgb_to_hex(bg), outline="", tags=tag
                )

            if text_str.strip():
                font = self.fonts[(st.bold, st.italic)]
                self.canvas.create_text(
                    x1, y, text=text_str, anchor="nw",
                    fill=self._rgb_to_hex(fg), font=font, tags=tag
                )

            # Draw underline for SGR underline OR OSC 8 hyperlink text
            if st.underline or url:
                uy = y + self.cell_h - 2
                self.canvas.create_line(
                    x1, uy, x2, uy, fill=self._rgb_to_hex(fg), tags=tag
                )

            col = next_col

    def _on_close(self):
        try:
            self.root.tk.deletefilehandler(self.master_fd)
        except Exception:
            pass
        try:
            os.close(self.master_fd)
            os.kill(self.pid, signal.SIGHUP)
        except OSError:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.title("clownfish")

    app_icon = tk.PhotoImage(file=(Path(__file__).resolve().parent / "clownfish.png"))
    root.iconphoto(True, app_icon)

    app = TkTerminalApp(root, cols=80, rows=24)
    root.mainloop()
