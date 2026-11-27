"""Tkinter canvas rendering pipeline for terminal screens."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from clownfish.config import TerminalConfig
from clownfish.core.ligatures import segment_row_cells
from clownfish.core.models import DEFAULT_BG, Selection
from clownfish.core.screen import ScreenBuffer
from clownfish.core.search import SearchMatch


class TkCanvasRenderer:
    """Renders terminal cells, selection overlays, and cursor onto a Tkinter Canvas."""

    def __init__(self, canvas: tk.Canvas, config: TerminalConfig | None = None) -> None:
        self.canvas = canvas
        self.config = config or TerminalConfig()
        try:
            self.canvas.configure(highlightthickness=0, borderwidth=0)
        except (tk.TclError, AttributeError):
            pass

        font_family = self.config.font_family
        font_size = self.config.font_size
        self.fonts = {
            (False, False): tkfont.Font(family=font_family, size=font_size),
            (True, False): tkfont.Font(family=font_family, size=font_size, weight="bold"),
            (False, True): tkfont.Font(family=font_family, size=font_size, slant="italic"),
            (True, True): tkfont.Font(family=font_family, size=font_size, weight="bold", slant="italic"),
        }
        self.cell_w = self.fonts[(False, False)].measure("M")
        self.cell_h = self.fonts[(False, False)].metrics("linespace")
        self._last_cursor_state: tuple[int, int, bool, int, int] | None = None
        self._photo_images: dict[tuple[int, int, int, int], tk.PhotoImage] = {}

    @staticmethod
    def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def render(self, screen: ScreenBuffer, cols: int, rows: int) -> None:
        """Render dirty rows and update the cursor position and inline graphics."""
        if getattr(screen, "synchronized_output", False):
            return

        had_dirty = bool(screen.dirty_lines)
        if had_dirty:
            for r in list(screen.dirty_lines):
                if 0 <= r < rows:
                    self._render_row(screen, r, cols)
            screen.dirty_lines.clear()

        # Render inline Kitty graphics placements
        self._render_graphics(screen, cols, rows)

        cursor_state = (
            screen.cursor_x,
            screen.cursor_y,
            screen.cursor_visible,
            getattr(screen, "cursor_style", 2),
            screen.scroll_offset,
        )
        if not had_dirty and cursor_state == self._last_cursor_state:
            return

        self._last_cursor_state = cursor_state
        self.canvas.delete("cursor")
        if screen.cursor_visible and screen.scroll_offset == 0:
            cx = screen.cursor_x * self.cell_w
            cy = screen.cursor_y * self.cell_h
            style = getattr(screen, "cursor_style", 2)
            if style in (3, 4):  # Underline
                self.canvas.create_rectangle(
                    cx,
                    cy + self.cell_h - 2,
                    cx + self.cell_w,
                    cy + self.cell_h,
                    fill=self.config.cursor_color,
                    outline="",
                    tags="cursor",
                )
            elif style in (5, 6):  # Bar (I-beam)
                self.canvas.create_rectangle(
                    cx,
                    cy,
                    cx + 2,
                    cy + self.cell_h,
                    fill=self.config.cursor_color,
                    outline="",
                    tags="cursor",
                )
            else:  # Block
                self.canvas.create_rectangle(
                    cx,
                    cy,
                    cx + self.cell_w,
                    cy + self.cell_h,
                    fill=self.config.cursor_color,
                    outline="",
                    stipple="gray50",
                    tags="cursor",
                )

        # Enforce correct display layering
        self.canvas.tag_lower("bg_item")
        self.canvas.tag_raise("graphic_item")
        self.canvas.tag_raise("text_item")
        self.canvas.tag_raise("line_item")
        self.canvas.tag_raise("selection_box")
        self.canvas.tag_raise("search_highlight")
        self.canvas.tag_raise("cursor")

    def draw_selection(self, selection: Selection, cols: int) -> None:
        """Draw selection rectangles over selected character cells."""
        self.canvas.delete("selection_box")
        if selection.is_empty():
            return

        (c1, r1), (c2, r2) = selection.normalized()
        for r in range(r1, r2 + 1):
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else cols - 1
            x1 = sc * self.cell_w
            y1 = r * self.cell_h
            x2 = (ec + 1) * self.cell_w
            y2 = (r + 1) * self.cell_h

            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=self.config.selection_color, outline="", tags="selection_box"
            )

        self.canvas.tag_raise("text_item")
        self.canvas.tag_raise("line_item")
        self.canvas.tag_raise("cursor")

    def draw_search_matches(
        self,
        matches: list[SearchMatch],
        active_match: SearchMatch | None,
        screen: ScreenBuffer,
        cols: int,
        rows: int,
    ) -> None:
        """Draw highlight boxes on search match occurrences visible in viewport."""
        self.canvas.delete("search_highlight")
        if not matches:
            return

        sb_len = len(screen.scrollback)
        top_visible_absolute = sb_len - screen.scroll_offset

        for m in matches:
            canvas_row = m.absolute_row - top_visible_absolute
            if 0 <= canvas_row < rows:
                sc = max(0, min(cols - 1, m.start_col))
                ec = max(0, min(cols - 1, m.end_col - 1))
                x1 = sc * self.cell_w
                y1 = canvas_row * self.cell_h
                x2 = (ec + 1) * self.cell_w
                y2 = (canvas_row + 1) * self.cell_h

                is_active = m == active_match
                color = "#ff9900" if is_active else self.config.search_bg
                stipple = "gray50" if is_active else "gray25"
                self.canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=color,
                    outline="#ffffff" if is_active else "",
                    width=1,
                    stipple=stipple,
                    tags="search_highlight",
                )

        self.canvas.tag_raise("text_item")
        self.canvas.tag_raise("line_item")
        self.canvas.tag_raise("cursor")

    def _render_row(self, screen: ScreenBuffer, r: int, cols: int) -> None:
        tag = f"row_{r}"
        self.canvas.delete(tag)
        y = r * self.cell_h
        row_cells = screen.get_visible_row(r)
        enable_lig = getattr(self.config, "enable_ligatures", True)
        segments = segment_row_cells(row_cells, cols, enable_ligatures=enable_lig)

        # Batch contiguous same-color background spans
        current_bg = None
        bg_start_col = 0
        bg_end_col = 0

        for seg in segments:
            st = seg.style
            bg = st.fg if st.reverse else st.bg
            if bg != current_bg:
                if current_bg is not None and current_bg != DEFAULT_BG:
                    self.canvas.create_rectangle(
                        bg_start_col * self.cell_w,
                        y,
                        bg_end_col * self.cell_w,
                        y + self.cell_h,
                        fill=self.rgb_to_hex(current_bg),
                        outline="",
                        tags=(tag, "bg_item"),
                    )
                current_bg = bg
                bg_start_col = seg.start_col
            bg_end_col = seg.end_col

        if current_bg is not None and current_bg != DEFAULT_BG:
            self.canvas.create_rectangle(
                bg_start_col * self.cell_w,
                y,
                bg_end_col * self.cell_w,
                y + self.cell_h,
                fill=self.rgb_to_hex(current_bg),
                outline="",
                tags=(tag, "bg_item"),
            )

        # Draw text chunks and underline / hyperlink indicators
        for seg in segments:
            st = seg.style
            fg = st.bg if st.reverse else st.fg
            x1 = seg.start_col * self.cell_w
            x2 = seg.end_col * self.cell_w

            if seg.text.strip():
                font = self.fonts[(st.bold, st.italic)]
                text_tags = (tag, "text_item", "ligature_item") if seg.is_ligature else (tag, "text_item")
                self.canvas.create_text(
                    x1,
                    y,
                    text=seg.text,
                    anchor="nw",
                    fill=self.rgb_to_hex(fg),
                    font=font,
                    tags=text_tags,
                )

            if st.underline or seg.url:
                uy = y + self.cell_h - 2
                self.canvas.create_line(
                    x1, uy, x2, uy, fill=self.rgb_to_hex(fg), tags=(tag, "line_item")
                )

    @staticmethod
    def _scale_photo(photo: tk.PhotoImage, target_w: int, target_h: int) -> tk.PhotoImage:
        """Scale a Tk PhotoImage to target dimensions while maintaining aspect ratio or exact fit."""
        cur_w = photo.width()
        cur_h = photo.height()
        if cur_w == target_w and cur_h == target_h:
            return photo
        if target_w <= 0 or target_h <= 0 or cur_w <= 0 or cur_h <= 0:
            return photo

        import math
        gcd_x = math.gcd(cur_w, target_w)
        gcd_y = math.gcd(cur_h, target_h)
        zx = target_w // gcd_x
        sx = cur_w // gcd_x
        zy = target_h // gcd_y
        sy = cur_h // gcd_y

        if cur_w * zx <= 2048 and cur_h * zy <= 2048:
            res = photo
            if zx > 1 or zy > 1:
                res = res.zoom(zx, zy)
            if sx > 1 or sy > 1:
                res = res.subsample(sx, sy)
            return res

        if cur_w >= target_w and cur_h >= target_h:
            return photo.subsample(max(1, round(cur_w / target_w)), max(1, round(cur_h / target_h)))
        elif cur_w <= target_w and cur_h <= target_h:
            return photo.zoom(max(1, round(target_w / cur_w)), max(1, round(target_h / cur_h)))
        return photo

    def _render_graphics(self, screen: ScreenBuffer, cols: int, rows: int) -> None:
        """Render active inline Kitty graphics placements on the canvas."""
        placements = getattr(screen, "active_graphic_placements", [])
        active_tags: set[str] = set()

        if placements:
            top_visible_absolute = screen.total_lines_scrolled - screen.scroll_offset

            for p in placements:
                visible_row = p.abs_row - top_visible_absolute
                # Check if placement intersects the vertical viewport
                if -p.rows < visible_row < rows:
                    tag = f"graphic_{p.image_id}_{p.placement_id}"
                    active_tags.add(tag)

                    target_w = p.cols * self.cell_w
                    target_h = p.rows * self.cell_h
                    orig_w = p.pixel_width if p.pixel_width > 0 else target_w
                    orig_h = p.pixel_height if p.pixel_height > 0 else target_h
                    scale = min(target_w / orig_w, target_h / orig_h)
                    fit_w = max(1, round(orig_w * scale))
                    fit_h = max(1, round(orig_h * scale))

                    cache_key = (p.image_id, p.version, fit_w, fit_h)

                    if cache_key not in self._photo_images and p.base64_data:
                        try:
                            raw_photo = tk.PhotoImage(data=p.base64_data, format=p.format)
                            scaled_photo = self._scale_photo(raw_photo, fit_w, fit_h)
                            self._photo_images[cache_key] = scaled_photo
                        except (tk.TclError, RuntimeError, ValueError):
                            pass

                    photo = self._photo_images.get(cache_key)
                    if photo:
                        gx = p.col * self.cell_w
                        gy = visible_row * self.cell_h
                        existing = self.canvas.find_withtag(tag)
                        if existing:
                            self.canvas.coords(tag, gx, gy)
                        else:
                            self.canvas.create_image(
                                gx, gy, image=photo, anchor="nw", tags=(tag, "graphic_item")
                            )

        # Cleanup scrolled-off or deleted graphic items from canvas
        for item in self.canvas.find_withtag("graphic_item"):
            item_tags = self.canvas.gettags(item)
            matched = any(t in active_tags for t in item_tags)
            if not matched:
                self.canvas.delete(item)

        # Prune cached PhotoImages no longer in active screen placements
        if placements:
            active_ids = {p.image_id for p in placements}
            for cached_key in list(self._photo_images.keys()):
                if cached_key[0] not in active_ids:
                    del self._photo_images[cached_key]
        elif self._photo_images:
            self._photo_images.clear()
            self.canvas.delete("graphic_item")

