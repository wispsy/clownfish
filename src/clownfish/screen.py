"""Screen buffer managing the active grid, alternate screen, and scrollback history."""

from collections import deque
from typing import ClassVar

from clownfish.models import DEFAULT_BG, DEFAULT_FG, Cell, Style


class ScreenBuffer:
    """Manages 2D character grid, cursor state, scroll regions, and history buffer."""

    ANSI_16: ClassVar[tuple[tuple[int, int, int], ...]] = (
        (20, 20, 25),     (205, 49, 49),    (13, 188, 121),   (229, 229, 16),
        (36, 114, 200),   (188, 63, 188),   (17, 168, 205),   (229, 229, 229),
        (102, 102, 102),  (241, 76, 76),    (35, 209, 139),   (245, 245, 67),
        (59, 142, 234),   (214, 112, 214),  (41, 184, 219),   (255, 255, 255),
    )

    def __init__(self, cols: int = 80, rows: int = 24, max_scrollback: int = 10_000):
        self.cols = cols
        self.rows = rows
        self.cursor_x = 0
        self.cursor_y = 0
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

        self.alt_grid: list[list[Cell]] = [self._blank_row() for _ in range(rows)]
        self.is_alt_screen = False
        self._primary_saved_cursor = (0, 0)
        self._primary_saved_style = Style()

        self.grid = self.primary_grid

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
        self.grid = [self._blank_row() for _ in range(self.rows)]
        if self.is_alt_screen:
            self.alt_grid = self.grid
        else:
            self.primary_grid = self.grid
        self.cursor_x = 0
        self.cursor_y = 0
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
            for y in range(self.cursor_y):
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
            for x in range(min(self.cursor_x + 1, self.cols)):
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

        def _resize_target(grid: list[list[Cell]], push_to_history: bool = False):
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

    def handle_sgr(self, params: list[int]):
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

    def _parse_extended_color(self, sub: list[int]) -> tuple[tuple[int, int, int] | None, int]:
        if not sub:
            return None, 0
        if sub[0] == 2 and len(sub) >= 4:
            return (sub[1], sub[2], sub[3]), 4
        elif sub[0] == 5 and len(sub) >= 2:
            return self._index_to_rgb(sub[1]), 2
        return None, 0

    @classmethod
    def _index_to_rgb(cls, idx: int) -> tuple[int, int, int]:
        if idx < 16:
            return cls.ANSI_16[idx]
        elif idx <= 231:
            idx -= 16
            return ((idx // 36) % 6 * 51, (idx // 6) % 6 * 51, (idx % 6) * 51)
        elif idx <= 255:
            g = (idx - 232) * 10 + 8
            return (g, g, g)
        return DEFAULT_FG
