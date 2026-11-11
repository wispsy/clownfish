"""Tkinter-based terminal emulator application."""

import codecs
import fcntl
import os
import pty
import signal
import struct
import sys
import termios
import tkinter as tk
import tkinter.font as tkfont
import webbrowser

from clownfish.models import DEFAULT_BG, WORD_DELIMITERS, Selection, encode_kitty_key
from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer


class TkTerminalApp:
    """Tkinter-based GUI terminal emulator connected to a local PTY."""

    def __init__(self, root: tk.Tk, cols: int = 80, rows: int = 24):
        self.root = root
        self.cols = cols
        self.rows = rows
        self._resize_job: str | None = None
        self.selection = Selection()

        self.screen = ScreenBuffer(cols=cols, rows=rows, max_scrollback=10_000)
        self.parser = VT100Parser(self.screen, write_response=self._write_master)
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

        # Clear screen + scrollback shortcuts
        if sys.platform == "darwin":
            self.root.bind("<Command-k>", self._on_clear_screen_shortcut)
            self.root.bind("<Command-K>", self._on_clear_screen_shortcut)
        else:
            self.root.bind("<Control-Shift-k>", self._on_clear_screen_shortcut)
            self.root.bind("<Control-Shift-K>", self._on_clear_screen_shortcut)

        # Semantic prompt jumping (OSC 133)
        self.canvas.bind("<Command-Up>", lambda e: self._jump_prompt(-1))
        self.canvas.bind("<Command-Down>", lambda e: self._jump_prompt(1))
        self.canvas.bind("<Control-Up>", lambda e: self._jump_prompt(-1))
        self.canvas.bind("<Control-Down>", lambda e: self._jump_prompt(1))

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

    def _write_master(self, data: bytes):
        try:
            os.write(self.master_fd, data)
        except OSError:
            pass

    @staticmethod
    def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def _set_pty_size(self, rows: int, cols: int):
        winsize = struct.pack("HHHH", rows, cols, cols * self.cell_w, rows * self.cell_h)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)

    def _pixel_to_cell(self, x: int, y: int) -> tuple[int, int]:
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
            packet = f"\x1b[<{button};{col + 1};{row + 1}{final}".encode()
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
        if cell.url and (event.state & 0x4 or (sys.platform == "darwin" and event.state & 0x8)):
            # Ctrl+Click (or Cmd+Click on macOS) opens link
            webbrowser.open(cell.url)
            return

        self.selection = Selection(
            active=True,
            start_col=col,
            start_row=row,
            end_col=col,
            end_row=row,
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
            end_row=row,
        )
        self._draw_selection_overlay()

    def _on_triple_click(self, event: tk.Event):
        if self.parser.mouse_tracking:
            return
        _col, row = self._pixel_to_cell(event.x, event.y)
        self.selection = Selection(
            active=True,
            start_col=0,
            start_row=row,
            end_col=self.cols - 1,
            end_row=row,
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

    def _on_mouse_scroll(self, delta: int, event: tk.Event | None = None):
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

    def _copy_selection_to_clipboard(self, event: tk.Event | None = None) -> str:
        if self.selection.is_empty():
            return "break"

        (c1, r1), (c2, r2) = self.selection.normalized()
        lines = []

        for r in range(r1, r2 + 1):
            row_cells = self.screen.get_visible_row(r)
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else self.cols - 1
            line_text = "".join(cell.char for cell in row_cells[sc : ec + 1] if cell.width != 0)
            lines.append(line_text.rstrip())

        selected_text = "\n".join(lines)
        if selected_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
            self.root.update()

        return "break"

    def _on_clear_screen_shortcut(self, event: tk.Event | None = None) -> str:
        # Wipe visual buffer and history
        self.screen.clear_all()
        self.canvas.delete("all")
        self.selection.active = False
        return "break"

    def _jump_prompt(self, direction: int) -> str:
        new_offset = self.screen.get_prompt_jump_offset(direction)
        if new_offset is not None:
            self.screen.scroll_offset = new_offset
            self.screen.mark_all_dirty()
            self.canvas.delete("selection_box")
            self.selection.active = False
        return "break"

    def _paste_from_clipboard(self, event: tk.Event | None = None) -> str:
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

        # Kitty keyboard protocol for modified keys
        if self.parser.kitty_keyboard_flags & 1:
            kitty_encoded = encode_kitty_key(event.keysym, event.state, event.char)
            if kitty_encoded is not None:
                os.write(self.master_fd, kitty_encoded)
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
            if cell.width == 0:
                col += 1
                continue

            st = cell.style
            url = cell.url
            fg = st.bg if st.reverse else st.fg
            bg = st.fg if st.reverse else st.bg

            if cell.width == 2:
                span_width = 2
                text_str = cell.char
                next_col = min(self.cols, col + 2)
            else:
                span_chars = [cell.char]
                next_col = col + 1
                while next_col < self.cols:
                    nc = row_cells[next_col]
                    if nc.width == 1 and nc.style == st and nc.url == url:
                        span_chars.append(nc.char)
                        next_col += 1
                    else:
                        break
                span_width = next_col - col
                text_str = "".join(span_chars)

            x1 = col * self.cell_w
            x2 = (col + span_width) * self.cell_w

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
        except (tk.TclError, OSError):
            pass
        try:
            os.close(self.master_fd)
            os.kill(self.pid, signal.SIGHUP)
        except OSError:
            pass
        self.root.destroy()
