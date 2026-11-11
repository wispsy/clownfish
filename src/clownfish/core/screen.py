"""Screen buffer managing the active grid, alternate screen, and scrollback history."""

from collections import deque
from typing import ClassVar

from clownfish.core.models import DEFAULT_BG, DEFAULT_FG, Cell, PromptMarker, Style, char_width


class ScreenBuffer:
    """Manages 2D character grid, cursor state, scroll regions, and history buffer."""

    ANSI_16: ClassVar[tuple[tuple[int, int, int], ...]] = (
        (20, 20, 25),     (205, 49, 49),    (13, 188, 121),   (229, 229, 16),
        (36, 114, 200),   (188, 63, 188),   (17, 168, 205),   (229, 229, 229),
        (102, 102, 102),  (241, 76, 76),    (35, 209, 139),   (245, 245, 67),
        (59, 142, 234),   (214, 112, 214),  (41, 184, 219),   (255, 255, 255),
    )

    # Standard xterm 6x6x6 color cube component levels
    CUBE_STEPS: ClassVar[tuple[int, ...]] = (0, 95, 135, 175, 215, 255)

    def __init__(self, cols: int = 80, rows: int = 24, max_scrollback: int = 10_000):
        self.cols = cols
        self.rows = rows
        self.cursor_x = 0
        self.cursor_y = 0
        self.wrap_pending = False
        self.cursor_visible = True
        self.saved_cursor = (0, 0)
        self.current_style = Style()
        self.current_url: str | None = None
        self.scroll_top = 0
        self.scroll_bottom = rows - 1
        self.dirty_lines: set[int] = set(range(rows))

        self.primary_grid: list[list[Cell]] = [self._blank_row() for _ in range(rows)]
        self.scrollback: deque[list[Cell]] = deque(maxlen=max_scrollback)
        self.scroll_offset = 0
        self.total_lines_scrolled = 0

        self.alt_grid: list[list[Cell]] = [self._blank_row() for _ in range(rows)]
        self.is_alt_screen = False
        self._primary_saved_cursor = (0, 0)
        self._primary_saved_style = Style()

        self.grid = self.primary_grid
        self.prompt_markers: list[PromptMarker] = []

    def _blank_row(self) -> list[Cell]:
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
        self.wrap_pending = False
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.erase_in_display(2)
        self.mark_all_dirty()

    def exit_alt_screen(self):
        if not self.is_alt_screen:
            return
        self.is_alt_screen = False
        self.grid = self.primary_grid
        # Note: prompt_markers are preserved across alternate screen switches
        self.cursor_x, self.cursor_y = self._primary_saved_cursor
        self.current_style = self._primary_saved_style.copy()
        self.wrap_pending = False
        self.scroll_top = 0
        self.scroll_bottom = self.rows - 1
        self.mark_all_dirty()

    def scroll_up(self, count: int = 1):
        for _ in range(count):
            popped = self.grid.pop(self.scroll_top)
            if not self.is_alt_screen and self.scroll_top == 0 and self.scroll_bottom == self.rows - 1:
                self.scrollback.append(popped)
                self.total_lines_scrolled += 1
            self.grid.insert(self.scroll_bottom, self._blank_row())

        if not self.is_alt_screen and self.scroll_offset > 0:
            self.scroll_offset = min(len(self.scrollback), self.scroll_offset + count)

        # Prune prompt markers older than scrollback history retention
        if len(self.prompt_markers) > 500:
            min_retained = self.total_lines_scrolled - (self.scrollback.maxlen or 10_000)
            self.prompt_markers = [m for m in self.prompt_markers if m.row >= min_retained]

        self.mark_all_dirty()

    def scroll_down(self, count: int = 1):
        for _ in range(count):
            del self.grid[self.scroll_bottom]
            self.grid.insert(self.scroll_top, self._blank_row())
        self.mark_all_dirty()

    def get_visible_row(self, r: int) -> list[Cell]:
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

    def clear_all(self):
        """Wipes the active grid and completely flushes the scrollback history."""
        self.scrollback.clear()
        self.scroll_offset = 0
        self.prompt_markers.clear()
        self.total_lines_scrolled = 0
        self.wrap_pending = False
        self.grid = [self._blank_row() for _ in range(self.rows)]
        if self.is_alt_screen:
            self.alt_grid = self.grid
        else:
            self.primary_grid = self.grid
        self.cursor_x = 0
        self.cursor_y = 0
        self.mark_all_dirty()

    def mark_prompt_start(self):
        """Record the start of a semantic shell prompt (OSC 133;A)."""
        abs_row = self.total_lines_scrolled + self.cursor_y
        marker = PromptMarker(row=abs_row)
        self.prompt_markers.append(marker)

    def mark_prompt_end(self):
        """Record prompt end / user command line start (OSC 133;B)."""

    def mark_command_executed(self):
        """Record user command execution start (OSC 133;C)."""

    def mark_command_finished(self, exit_code: int | None = None):
        """Record user command termination with exit status (OSC 133;D)."""
        if self.prompt_markers:
            self.prompt_markers[-1].exit_code = exit_code

    def get_prompt_jump_offset(self, direction: int) -> int | None:
        """Find the scrollback offset to jump to previous (direction < 0) or next (direction > 0) prompt."""
        if not self.prompt_markers:
            return None

        current_view_top = self.total_lines_scrolled - self.scroll_offset

        if direction < 0:
            candidates = [m.row for m in self.prompt_markers if m.row < current_view_top]
            if not candidates:
                earliest = self.prompt_markers[0].row
                if earliest < current_view_top:
                    target_row = earliest
                else:
                    return None
            else:
                target_row = max(candidates)
        else:
            candidates = [m.row for m in self.prompt_markers if m.row > current_view_top]
            if not candidates:
                if self.scroll_offset > 0:
                    return 0
                return None
            else:
                target_row = min(candidates)

        target_offset = self.total_lines_scrolled - target_row
        return max(0, min(len(self.scrollback), target_offset))

    def move_cursor(self, row: int, col: int):
        self.cursor_y = max(0, min(self.rows - 1, row))
        self.cursor_x = max(0, min(self.cols - 1, col))
        self.wrap_pending = False

    def save_cursor(self):
        self.saved_cursor = (self.cursor_x, self.cursor_y)

    def restore_cursor(self):
        self.cursor_x, self.cursor_y = self.saved_cursor
        self.wrap_pending = False

    def put_char(self, char: str):
        w = char_width(char)
        if w == 0:
            # Combining character or zero-width: attach to previous cell
            prev_x = max(0, self.cursor_x - 1)
            target_cell = self.grid[self.cursor_y][prev_x]
            if target_cell.width == 0 and prev_x > 0:
                target_cell = self.grid[self.cursor_y][prev_x - 1]
            target_cell.char += char
            self.dirty_lines.add(self.cursor_y)
            return

        # Handle pending autowrap delay when writing the next printable character
        if self.wrap_pending:
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y > self.scroll_bottom:
                self.scroll_up(1)
                self.cursor_y = self.scroll_bottom
            self.wrap_pending = False

        if w == 2 and self.cursor_x >= self.cols - 1:
            # Wide glyph cannot fit in final single column, wrap immediately
            if self.cursor_x == self.cols - 1:
                self.grid[self.cursor_y][self.cursor_x] = Cell(
                    char=" ",
                    style=self.current_style.copy(),
                    url=self.current_url,
                    width=1,
                )
            self.cursor_x = 0
            self.cursor_y += 1
            if self.cursor_y > self.scroll_bottom:
                self.scroll_up(1)
                self.cursor_y = self.scroll_bottom

        # If overwriting a spacer cell of a previous wide character, blank out leader
        if self.grid[self.cursor_y][self.cursor_x].width == 0 and self.cursor_x > 0:
            self.grid[self.cursor_y][self.cursor_x - 1] = Cell(
                char=" ",
                style=self.current_style.copy(),
                url=self.current_url,
                width=1,
            )

        self.grid[self.cursor_y][self.cursor_x] = Cell(
            char=char,
            style=self.current_style.copy(),
            url=self.current_url,
            width=w,
        )
        self.dirty_lines.add(self.cursor_y)

        if w == 2:
            if self.cursor_x + 1 < self.cols:
                self.grid[self.cursor_y][self.cursor_x + 1] = Cell(
                    char="",
                    style=self.current_style.copy(),
                    url=self.current_url,
                    width=0,
                )
            if self.cursor_x + 2 >= self.cols:
                self.cursor_x = self.cols - 1
                self.wrap_pending = True
            else:
                self.cursor_x += 2
        else:
            if self.cursor_x == self.cols - 1:
                self.wrap_pending = True
            else:
                self.cursor_x += 1

    def erase_in_display(self, mode: int = 0):
        self.wrap_pending = False
        if mode == 0:
            self.erase_in_line(0)
            for y in range(self.cursor_y + 1, self.rows):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
        elif mode == 1:
            for y in range(self.cursor_y):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
            self.erase_in_line(1)
        elif mode == 2:
            self.grid = [self._blank_row() for _ in range(self.rows)]
            if self.is_alt_screen:
                self.alt_grid = self.grid
            else:
                self.primary_grid = self.grid
            self.mark_all_dirty()
        elif mode == 3:
            # CSI 3 J: Erase Saved Lines (xterm extension)
            self.scrollback.clear()
            self.scroll_offset = 0
            self.mark_all_dirty()

    def erase_in_line(self, mode: int = 0):
        self.wrap_pending = False
        y = self.cursor_y
        if mode == 0:
            for x in range(self.cursor_x, self.cols):
                self.grid[y][x] = Cell(style=self.current_style.copy())
        elif mode == 1:
            for x in range(min(self.cursor_x + 1, self.cols)):
                self.grid[y][x] = Cell(style=self.current_style.copy())
        elif mode == 2:
            self.grid[y] = self._blank_row()
        self.dirty_lines.add(y)

    def insert_chars(self, count: int):
        self.wrap_pending = False
        y, x = self.cursor_y, self.cursor_x
        for _ in range(count):
            self.grid[y].insert(x, Cell(style=self.current_style.copy(), url=self.current_url))
            self.grid[y].pop()
        self.dirty_lines.add(y)

    def delete_chars(self, count: int):
        self.wrap_pending = False
        y, x = self.cursor_y, self.cursor_x
        for _ in range(count):
            if x < len(self.grid[y]):
                self.grid[y].pop(x)
                self.grid[y].append(Cell(style=self.current_style.copy(), url=self.current_url))
        self.dirty_lines.add(y)

    def resize(self, new_cols: int, new_rows: int):
        if new_cols == self.cols and new_rows == self.rows:
            return

        self.wrap_pending = False

        def _resize_target(grid: list[list[Cell]], push_to_history: bool = False):
            if new_rows < self.rows:
                excess = self.rows - new_rows
                for _ in range(excess):
                    if grid:
                        popped = grid.pop(0)
                        if push_to_history:
                            self.scrollback.append(popped)
                            self.total_lines_scrolled += 1
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

    def handle_sgr(self, param_groups: list[list[int]]):
        if not param_groups:
            param_groups = [[0]]
        i = 0
        while i < len(param_groups):
            group = param_groups[i]
            if len(group) > 1:
                # Colon-separated subparameter format
                cmd = group[0]
                if cmd in (38, 48):
                    color = None
                    if group[1] == 2:
                        # TrueColor subparams: 38:2::r:g:b or 38:2:cs:r:g:b or 38:2:r:g:b
                        if len(group) >= 6 and group[2] == 0:
                            color = (group[3], group[4], group[5])
                        elif len(group) >= 5:
                            color = (group[2], group[3], group[4])
                    elif group[1] == 5 and len(group) >= 3:
                        # 256 indexed: 38:5:idx
                        color = self._index_to_rgb(group[2])
                    if color:
                        if cmd == 38:
                            self.current_style.fg = color
                        else:
                            self.current_style.bg = color
                elif cmd == 4:
                    self.current_style.underline = (group[1] != 0)
                i += 1
                continue

            # Standard semicolon-separated parameter
            p = group[0]
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
                # Standard semicolon-separated extended color:
                # 38;2;r;g;b (consumes next 4) or 38;5;idx (consumes next 2)
                if i + 4 < len(param_groups) and param_groups[i + 1][0] == 2:
                    color = (param_groups[i + 2][0], param_groups[i + 3][0], param_groups[i + 4][0])
                    if p == 38:
                        self.current_style.fg = color
                    else:
                        self.current_style.bg = color
                    i += 4
                elif i + 2 < len(param_groups) and param_groups[i + 1][0] == 5:
                    color = self._index_to_rgb(param_groups[i + 2][0])
                    if p == 38:
                        self.current_style.fg = color
                    else:
                        self.current_style.bg = color
                    i += 2
            i += 1

    @classmethod
    def _index_to_rgb(cls, idx: int) -> tuple[int, int, int]:
        if idx < 16:
            return cls.ANSI_16[idx]
        elif idx <= 231:
            idx -= 16
            r = cls.CUBE_STEPS[(idx // 36) % 6]
            g = cls.CUBE_STEPS[(idx // 6) % 6]
            b = cls.CUBE_STEPS[idx % 6]
            return (r, g, b)
        elif idx <= 255:
            g = (idx - 232) * 10 + 8
            return (g, g, g)
        return DEFAULT_FG
