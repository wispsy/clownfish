"""Screen buffer managing the active grid, alternate screen, and scrollback history."""

from collections import deque
from typing import ClassVar

from clownfish.core.models import (
    DEFAULT_BG,
    DEFAULT_FG,
    Cell,
    GraphicImage,
    GraphicPlacement,
    PromptMarker,
    Row,
    Style,
    char_width,
)


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

        # VT Modes & Attributes
        self.origin_mode: bool = False
        self.auto_wrap: bool = True
        self.cursor_style: int = 2  # 0/1: blink block, 2: steady block, 3/4: underline, 5/6: bar
        self.synchronized_output: bool = False

        self.primary_grid: list[Row] = [self._blank_row() for _ in range(rows)]
        self.scrollback: deque[Row] = deque(maxlen=max_scrollback)
        self.scroll_offset = 0
        self.total_lines_scrolled = 0

        self.alt_grid: list[Row] = [self._blank_row() for _ in range(rows)]
        self.is_alt_screen = False
        self._primary_saved_cursor = (0, 0)
        self._primary_saved_style = Style()

        self.grid = self.primary_grid
        self.prompt_markers: list[PromptMarker] = []
        self.stored_graphics: dict[int, GraphicImage] = {}
        self.graphic_memory_bytes: int = 0
        self.graphic_placements: list[GraphicPlacement] = []
        self.alt_graphic_placements: list[GraphicPlacement] = []
        self.title: str = ""
        self.icon_name: str = ""
        self.cwd: str = ""

    MAX_GRAPHIC_STORE_BYTES: int = 32 * 1024 * 1024  # 32 MB total graphics store limit

    def _blank_row(self, cols: int | None = None, is_wrapped: bool = False) -> Row:
        c = cols if cols is not None else self.cols
        return Row(
            [Cell(style=self.current_style.copy(), url=self.current_url) for _ in range(c)],
            is_wrapped=is_wrapped,
        )

    def store_graphic(self, image: GraphicImage) -> None:
        """Store or update a graphic image in memory with total memory budgeting."""
        if image.image_id in self.stored_graphics:
            old_img = self.stored_graphics[image.image_id]
            self.graphic_memory_bytes = max(0, self.graphic_memory_bytes - len(old_img.data))
            image.version = old_img.version + 1

        image_size = len(image.data)
        if image_size > self.MAX_GRAPHIC_STORE_BYTES:
            return

        active_img_ids = {p.image_id for p in self.graphic_placements} | {p.image_id for p in self.alt_graphic_placements}
        while self.graphic_memory_bytes + image_size > self.MAX_GRAPHIC_STORE_BYTES and self.stored_graphics:
            candidates = [iid for iid in self.stored_graphics if iid not in active_img_ids]
            if not candidates:
                candidates = list(self.stored_graphics.keys())
            evict_id = candidates[0]
            evicted = self.stored_graphics.pop(evict_id)
            self.graphic_memory_bytes = max(0, self.graphic_memory_bytes - len(evicted.data))
            self.graphic_placements[:] = [p for p in self.graphic_placements if p.image_id != evict_id]
            self.alt_graphic_placements[:] = [p for p in self.alt_graphic_placements if p.image_id != evict_id]

        self.stored_graphics[image.image_id] = image
        self.graphic_memory_bytes += image_size

        # Synchronize active placements with the updated image data and version
        target_lists = [self.graphic_placements, self.alt_graphic_placements]
        for t_list in target_lists:
            for p in t_list:
                if p.image_id == image.image_id:
                    p.version = image.version
                    p.data = image.data
                    p.format = image.format
                    p.base64_data = image.base64_data
                    p.pixel_width = image.pixel_width
                    p.pixel_height = image.pixel_height
                    for r in range(p.row, min(self.rows, p.row + p.rows)):
                        self.dirty_lines.add(r)

    def get_stored_graphic(self, image_id: int) -> GraphicImage | None:
        """Lookup stored graphic by ID."""
        return self.stored_graphics.get(image_id)

    @property
    def active_graphic_placements(self) -> list[GraphicPlacement]:
        """Return the graphic placements corresponding to the active screen buffer."""
        return self.alt_graphic_placements if self.is_alt_screen else self.graphic_placements

    def add_graphic_placement(self, placement: GraphicPlacement) -> None:
        """Register a new graphic placement in the active screen buffer."""
        if placement.image_id in self.stored_graphics:
            img = self.stored_graphics[placement.image_id]
            if not placement.data:
                placement.data = img.data
            if not placement.format:
                placement.format = img.format
            if not placement.base64_data:
                placement.base64_data = img.base64_data
            if placement.pixel_width == 0:
                placement.pixel_width = img.pixel_width
            if placement.pixel_height == 0:
                placement.pixel_height = img.pixel_height
            placement.version = img.version

        target_list = self.alt_graphic_placements if self.is_alt_screen else self.graphic_placements
        target_list.append(placement)
        for r in range(placement.row, min(self.rows, placement.row + placement.rows)):
            self.dirty_lines.add(r)

    def delete_graphic_placements(
        self,
        target: str = "all",
        image_id: int | None = None,
        placement_id: int | None = None,
    ) -> None:
        """Delete graphic placements matching criteria."""
        if target == "all":
            self.graphic_placements.clear()
            self.alt_graphic_placements.clear()
            self.stored_graphics.clear()
            self.graphic_memory_bytes = 0
        elif target == "image" and image_id is not None:
            self.graphic_placements[:] = [p for p in self.graphic_placements if p.image_id != image_id]
            self.alt_graphic_placements[:] = [p for p in self.alt_graphic_placements if p.image_id != image_id]
            old = self.stored_graphics.pop(image_id, None)
            if old:
                self.graphic_memory_bytes = max(0, self.graphic_memory_bytes - len(old.data))
        elif target == "placement" and placement_id is not None:
            if image_id is not None and image_id > 0:
                self.graphic_placements[:] = [
                    p for p in self.graphic_placements if not (p.image_id == image_id and p.placement_id == placement_id)
                ]
                self.alt_graphic_placements[:] = [
                    p for p in self.alt_graphic_placements if not (p.image_id == image_id and p.placement_id == placement_id)
                ]
            else:
                self.graphic_placements[:] = [p for p in self.graphic_placements if p.placement_id != placement_id]
                self.alt_graphic_placements[:] = [p for p in self.alt_graphic_placements if p.placement_id != placement_id]
        self.mark_all_dirty()

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

        # Prune graphic placements older than scrollback history retention
        if not self.is_alt_screen and self.graphic_placements:
            min_retained = self.total_lines_scrolled - (self.scrollback.maxlen or 10_000)
            self.graphic_placements = [
                p for p in self.graphic_placements if (p.abs_row + p.rows) >= min_retained
            ]

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
            row = self.scrollback[target_idx]
            if len(row) < self.cols:
                row.extend([Cell(char=" ", style=Style()) for _ in range(self.cols - len(row))])
            return row
        else:
            grid_idx = target_idx - history_len
            if grid_idx < self.rows:
                row = self.grid[grid_idx]
                if len(row) < self.cols:
                    row.extend([Cell(char=" ", style=Style()) for _ in range(self.cols - len(row))])
                return row
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
        self.graphic_placements.clear()
        self.alt_graphic_placements.clear()
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
        min_r = self.scroll_top if self.origin_mode else 0
        max_r = self.scroll_bottom if self.origin_mode else (self.rows - 1)
        self.cursor_y = max(min_r, min(max_r, row))
        self.cursor_x = max(0, min(self.cols - 1, col))
        self.wrap_pending = False

    def save_cursor(self):
        self.saved_cursor = (self.cursor_x, self.cursor_y)

    def restore_cursor(self):
        self.cursor_x, self.cursor_y = self.saved_cursor
        self.wrap_pending = False

    def put_char(self, char: str):
        w = char_width(char)
        prev_x = max(0, self.cursor_x - 1)
        target_cell = self.grid[self.cursor_y][prev_x]
        if target_cell.width == 0 and prev_x > 0:
            target_cell = self.grid[self.cursor_y][prev_x - 1]

        if w == 0:
            # Combining character or zero-width: attach to previous cell
            target_cell.char += char
            self.dirty_lines.add(self.cursor_y)
            return

        # Check if previous cell ended with ZWJ (\u200D) - ZWJ continuation sequence
        if target_cell.char and target_cell.char.endswith("\u200d"):
            target_cell.char += char
            self.dirty_lines.add(self.cursor_y)
            return

        # Check for Regional Indicator flag pairing (e.g. 🇯 + 🇵)
        if (
            len(char) == 1
            and 0x1F1E6 <= ord(char) <= 0x1F1FF
            and target_cell.char
            and len(target_cell.char) == 1
            and 0x1F1E6 <= ord(target_cell.char) <= 0x1F1FF
        ):
            target_cell.char += char
            target_cell.width = 2
            self.dirty_lines.add(self.cursor_y)
            return

        # Handle pending autowrap delay when writing the next printable character
        if self.wrap_pending:
            if self.auto_wrap:
                self.grid[self.cursor_y].is_wrapped = True
                self.cursor_x = 0
                self.cursor_y += 1
                if self.cursor_y > self.scroll_bottom:
                    self.scroll_up(1)
                    self.cursor_y = self.scroll_bottom
            self.wrap_pending = False

        if not self.auto_wrap:
            if self.cursor_x >= self.cols - 1:
                self.cursor_x = self.cols - 1
                if w == 2:
                    char = " "
                    w = 1
        elif w == 2 and self.cursor_x >= self.cols - 1:
            # Wide glyph cannot fit in final single column, wrap immediately
            if self.cursor_x == self.cols - 1:
                self.grid[self.cursor_y][self.cursor_x] = Cell(
                    char=" ",
                    style=self.current_style.copy(),
                    url=self.current_url,
                    width=1,
                )
            self.grid[self.cursor_y].is_wrapped = True
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

        if self.auto_wrap:
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
        else:
            if w == 2:
                if self.cursor_x + 1 < self.cols:
                    self.grid[self.cursor_y][self.cursor_x + 1] = Cell(
                        char="",
                        style=self.current_style.copy(),
                        url=self.current_url,
                        width=0,
                    )
                self.cursor_x = min(self.cols - 1, self.cursor_x + 2)
            else:
                self.cursor_x = min(self.cols - 1, self.cursor_x + 1)

    def erase_in_display(self, mode: int = 0):
        self.wrap_pending = False
        target_list = self.alt_graphic_placements if self.is_alt_screen else self.graphic_placements
        if mode == 0:
            self.erase_in_line(0)
            for y in range(self.cursor_y + 1, self.rows):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
            cursor_abs = self.total_lines_scrolled + self.cursor_y
            target_list[:] = [p for p in target_list if p.abs_row < cursor_abs]
        elif mode == 1:
            for y in range(self.cursor_y):
                self.grid[y] = self._blank_row()
                self.dirty_lines.add(y)
            self.erase_in_line(1)
            cursor_abs = self.total_lines_scrolled + self.cursor_y
            target_list[:] = [p for p in target_list if p.abs_row >= cursor_abs]
        elif mode == 2:
            self.grid = [self._blank_row() for _ in range(self.rows)]
            if self.is_alt_screen:
                self.alt_grid = self.grid
                self.alt_graphic_placements.clear()
            else:
                self.primary_grid = self.grid
                current_top = self.total_lines_scrolled
                self.graphic_placements[:] = [p for p in self.graphic_placements if p.abs_row < current_top]
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

    def erase_chars(self, count: int = 1) -> None:
        """Erase characters from current cursor position without shifting (CSI X / ECH)."""
        self.wrap_pending = False
        y, x = self.cursor_y, self.cursor_x
        end_x = min(self.cols, x + max(1, count))
        for col in range(x, end_x):
            self.grid[y][col] = Cell(char=" ", style=self.current_style.copy(), url=self.current_url)
        self.dirty_lines.add(y)

    def insert_lines(self, count: int = 1) -> None:
        """Insert blank lines at cursor line within scroll region (CSI L / IL)."""
        self.wrap_pending = False
        if not (self.scroll_top <= self.cursor_y <= self.scroll_bottom):
            return
        count = min(count, self.scroll_bottom - self.cursor_y + 1)
        for _ in range(count):
            self.grid.insert(self.cursor_y, self._blank_row())
            del self.grid[self.scroll_bottom + 1]
        self.mark_all_dirty()

    def delete_lines(self, count: int = 1) -> None:
        """Delete lines at cursor line within scroll region (CSI M / DL)."""
        self.wrap_pending = False
        if not (self.scroll_top <= self.cursor_y <= self.scroll_bottom):
            return
        count = min(count, self.scroll_bottom - self.cursor_y + 1)
        for _ in range(count):
            del self.grid[self.cursor_y]
            self.grid.insert(self.scroll_bottom, self._blank_row())
        self.mark_all_dirty()

    def clear_saved_lines(self) -> None:
        """Clear scrollback history without modifying visible screen."""
        self.scrollback.clear()
        self.scroll_offset = 0
        self.mark_all_dirty()

    def resize(self, new_cols: int, new_rows: int) -> None:
        if new_cols == self.cols and new_rows == self.rows:
            return

        self.wrap_pending = False

        if self.is_alt_screen:
            self._resize_alt_screen(new_cols, new_rows)
            self._reflow_primary(new_cols, new_rows)
        else:
            self._reflow_primary(new_cols, new_rows)

        self.cols = new_cols
        self.rows = new_rows
        self.scroll_top = 0
        self.scroll_bottom = new_rows - 1
        self.cursor_x = max(0, min(self.cols - 1, self.cursor_x))
        self.cursor_y = max(0, min(self.rows - 1, self.cursor_y))
        self.mark_all_dirty()

    def _resize_alt_screen(self, new_cols: int, new_rows: int) -> None:
        """Resize alternate screen grid by padding/clipping without text reflow."""
        old_rows = self.rows

        for r in range(len(self.alt_grid)):
            curr_len = len(self.alt_grid[r])
            if new_cols > curr_len:
                self.alt_grid[r].extend(
                    [Cell(style=self.current_style.copy()) for _ in range(new_cols - curr_len)]
                )
            elif new_cols < curr_len:
                self.alt_grid[r] = Row(self.alt_grid[r][:new_cols], is_wrapped=False)

        if new_rows > old_rows:
            for _ in range(new_rows - old_rows):
                self.alt_grid.append(self._blank_row(new_cols))
        elif new_rows < old_rows:
            self.alt_grid = self.alt_grid[:new_rows]

        if self.is_alt_screen:
            self.grid = self.alt_grid

    def _reflow_primary(self, new_cols: int, new_rows: int) -> None:
        """Reflow logical lines across scrollback and primary grid into new column width."""
        all_rows: list[Row] = list(self.scrollback) + list(self.primary_grid)
        if self.is_alt_screen:
            p_x, p_y = self._primary_saved_cursor
            cursor_abs_row = len(self.scrollback) + p_y
            cursor_abs_col = p_x
        else:
            cursor_abs_row = len(self.scrollback) + self.cursor_y
            cursor_abs_col = self.cursor_x

        # Only reflow up to the last active row with content, cursor, or prompt markers
        last_active_row = cursor_abs_row
        for m in self.prompt_markers:
            last_active_row = max(last_active_row, m.row)
        for r_idx in range(len(all_rows) - 1, -1, -1):
            row = all_rows[r_idx]
            has_content = any(c.char not in (" ", "") or not c.style.is_default() or c.url is not None for c in row)
            if has_content or row.is_wrapped:
                last_active_row = max(last_active_row, r_idx)
                break

        active_rows = all_rows[: last_active_row + 1]
        base_abs = max(0, self.total_lines_scrolled - len(self.scrollback))

        logical_lines: list[tuple[list[Cell], int | None, list[PromptMarker], list[tuple[int, int]]]] = []
        current_cells: list[Cell] = []
        cursor_offset: int | None = None
        markers_for_line: list[PromptMarker] = []
        line_orig_rows: list[tuple[int, int]] = []

        for r_idx, row in enumerate(active_rows):
            line_orig_rows.append((r_idx, len(current_cells)))
            for m in self.prompt_markers:
                if m.row == r_idx:
                    markers_for_line.append(m)

            is_cursor_row = (r_idx == cursor_abs_row)

            if row.is_wrapped:
                if is_cursor_row:
                    cursor_offset = len(current_cells) + cursor_abs_col
                current_cells.extend(row)
            else:
                last_content = -1
                for c_idx in range(len(row) - 1, -1, -1):
                    c = row[c_idx]
                    if c.char not in (" ", "") or not c.style.is_default() or c.url is not None:
                        last_content = c_idx
                        break
                if is_cursor_row:
                    last_content = max(last_content, cursor_abs_col)

                content_cells = row[: last_content + 1] if last_content >= 0 else []

                if is_cursor_row:
                    cursor_offset = len(current_cells) + cursor_abs_col

                current_cells.extend(content_cells)

                logical_lines.append((current_cells, cursor_offset, markers_for_line, line_orig_rows))
                current_cells = []
                cursor_offset = None
                markers_for_line = []
                line_orig_rows = []

        if current_cells or cursor_offset is not None or markers_for_line or line_orig_rows:
            logical_lines.append((current_cells, cursor_offset, markers_for_line, line_orig_rows))

        new_all_rows: list[Row] = []
        new_cursor_abs_row = 0
        new_cursor_col = 0
        new_prompt_markers: list[PromptMarker] = []
        row_offset_to_new_pos: dict[int, tuple[int, int]] = {}

        for cells, cur_offset, markers, orig_row_data in logical_lines:
            line_start_row = len(new_all_rows)
            for orig_r, cell_off in orig_row_data:
                row_offset_to_new_pos[orig_r] = (line_start_row, cell_off)

            for m in markers:
                m.row = line_start_row
                new_prompt_markers.append(m)

            if not cells:
                if cur_offset is not None:
                    new_cursor_abs_row = len(new_all_rows)
                    new_cursor_col = 0
                new_all_rows.append(self._blank_row(new_cols, is_wrapped=False))
                continue

            idx = 0
            while idx < len(cells):
                row_cells: list[Cell] = []
                while len(row_cells) < new_cols and idx < len(cells):
                    c = cells[idx]
                    if c.width == 2 and len(row_cells) == new_cols - 1:
                        # Cannot fit wide char in last column; pad space and wrap
                        row_cells.append(Cell(char=" ", style=c.style.copy()))
                        break

                    if cur_offset is not None and idx == cur_offset:
                        new_cursor_abs_row = len(new_all_rows)
                        new_cursor_col = len(row_cells)

                    row_cells.append(c)
                    idx += 1

                    if idx < len(cells) and cells[idx].width == 0:
                        if cur_offset is not None and idx == cur_offset:
                            new_cursor_abs_row = len(new_all_rows)
                            new_cursor_col = len(row_cells)
                        row_cells.append(cells[idx])
                        idx += 1

                if idx < len(cells):
                    new_all_rows.append(Row(row_cells, is_wrapped=True))
                else:
                    if cur_offset is not None and cur_offset >= len(cells):
                        new_cursor_abs_row = len(new_all_rows)
                        new_cursor_col = min(len(row_cells), new_cols - 1)
                    while len(row_cells) < new_cols:
                        row_cells.append(Cell(char=" ", style=Style()))
                    new_all_rows.append(Row(row_cells, is_wrapped=False))

        total_new = len(new_all_rows)
        if total_new >= new_rows:
            self.primary_grid = new_all_rows[-new_rows:]
            self.scrollback = deque(new_all_rows[:-new_rows], maxlen=self.scrollback.maxlen)
            prim_y = max(0, min(new_rows - 1, new_cursor_abs_row - (total_new - new_rows)))
        else:
            self.scrollback = deque(maxlen=self.scrollback.maxlen)
            self.primary_grid = new_all_rows
            while len(self.primary_grid) < new_rows:
                self.primary_grid.append(self._blank_row(new_cols, is_wrapped=False))
            prim_y = max(0, min(new_rows - 1, new_cursor_abs_row))

        prim_x = max(0, min(new_cols - 1, new_cursor_col))
        if self.is_alt_screen:
            self._primary_saved_cursor = (prim_x, prim_y)
        else:
            self.cursor_y = prim_y
            self.cursor_x = prim_x

        self.total_lines_scrolled = len(self.scrollback)
        self.scroll_offset = max(0, min(len(self.scrollback), self.scroll_offset))
        self.prompt_markers = new_prompt_markers

        # Remap graphic placements with precise cell anchoring within logical lines
        for p in self.graphic_placements:
            orig_r_idx = p.abs_row - base_abs
            if orig_r_idx in row_offset_to_new_pos:
                line_start, cell_off = row_offset_to_new_pos[orig_r_idx]
                total_cell_off = cell_off + p.col
                p.abs_row = line_start + (total_cell_off // new_cols)
                p.col = total_cell_off % new_cols
            elif orig_r_idx > last_active_row:
                p.abs_row = max(0, p.abs_row + (len(new_all_rows) - len(active_rows)))

        # Prune placements that scrolled past maximum scrollback retention
        min_retained_abs_row = max(0, self.total_lines_scrolled - (self.scrollback.maxlen or 10_000))
        self.graphic_placements[:] = [p for p in self.graphic_placements if p.abs_row >= min_retained_abs_row]

        if not self.is_alt_screen:
            self.grid = self.primary_grid

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
