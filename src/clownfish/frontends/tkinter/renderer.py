"""Tkinter canvas rendering pipeline for terminal screens."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont

from clownfish.config import TerminalConfig
from clownfish.core.models import DEFAULT_BG, Selection
from clownfish.core.screen import ScreenBuffer


class TkCanvasRenderer:
    """Renders terminal cells, selection overlays, and cursor onto a Tkinter Canvas."""

    def __init__(self, canvas: tk.Canvas, config: TerminalConfig | None = None) -> None:
        self.canvas = canvas
        self.config = config or TerminalConfig()

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

    @staticmethod
    def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
        return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

    def render(self, screen: ScreenBuffer, cols: int, rows: int) -> None:
        """Render dirty rows and update the cursor position."""
        if screen.dirty_lines:
            for r in list(screen.dirty_lines):
                if 0 <= r < rows:
                    self._render_row(screen, r, cols)
            screen.dirty_lines.clear()

        self.canvas.delete("cursor")
        if screen.cursor_visible and screen.scroll_offset == 0:
            cx = screen.cursor_x * self.cell_w
            cy = screen.cursor_y * self.cell_h
            self.canvas.create_rectangle(
                cx, cy, cx + self.cell_w, cy + self.cell_h,
                fill=self.config.cursor_color, outline="", stipple="gray50", tags="cursor"
            )

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
                fill=self.config.selection_color, outline="", stipple="gray50", tags="selection_box"
            )

        self.canvas.tag_raise("cursor")

    def _render_row(self, screen: ScreenBuffer, r: int, cols: int) -> None:
        tag = f"row_{r}"
        self.canvas.delete(tag)
        y = r * self.cell_h
        row_cells = screen.get_visible_row(r)

        col = 0
        while col < cols:
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
                next_col = min(cols, col + 2)
            else:
                span_chars = [cell.char]
                next_col = col + 1
                while next_col < cols:
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
                    fill=self.rgb_to_hex(bg), outline="", tags=tag
                )

            if text_str.strip():
                font = self.fonts[(st.bold, st.italic)]
                self.canvas.create_text(
                    x1, y, text=text_str, anchor="nw",
                    fill=self.rgb_to_hex(fg), font=font, tags=tag
                )

            if st.underline or url:
                uy = y + self.cell_h - 2
                self.canvas.create_line(
                    x1, uy, x2, uy, fill=self.rgb_to_hex(fg), tags=tag
                )

            col = next_col
