"""Tkinter input event handling for keyboard and mouse interactions."""

from __future__ import annotations

import sys
import tkinter as tk
import urllib.parse
import webbrowser

from clownfish.core.models import WORD_DELIMITERS, Selection
from clownfish.session.session import TerminalSession


def is_application_shortcut(event: tk.Event) -> bool:
    """Return True if event represents an application-level menu/tab/window shortcut."""
    is_mac = sys.platform == "darwin"
    has_ctrl = bool(event.state & 0x4)
    has_shift = bool(event.state & 0x1)
    if is_mac:
        # On macOS TkAqua: Command is Mod1 (0x8), Option is Mod2 (0x10).
        # 0x40 is the hardware Fn/Arrow key flag and must not trigger has_cmd.
        has_cmd = bool(event.state & 0x8)
        has_alt = bool(event.state & 0x10)
    else:
        has_cmd = False
        has_alt = bool(event.state & 0x8 or event.state & 0x80)

    sym = event.keysym.lower()

    if is_mac and has_cmd:
        if sym in ("t", "w", "d", "f", "k", "c", "v", "bracketleft", "bracketright", "equal"):
            return True
        if event.keysym in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            return True
        if event.keysym in ("Up", "Down"):
            return True

    if has_ctrl and event.keysym in ("Tab", "ISO_Left_Tab"):
        return True

    if has_alt and sym in ("bracketleft", "bracketright"):
        return True

    if has_ctrl and sym in ("equal",):
        return True

    if has_ctrl and has_shift and sym in ("t", "w", "d", "f", "k", "c", "v"):
        return True

    if not is_mac and has_ctrl and event.keysym in ("Up", "Down"):
        return True

    return bool(has_alt and event.keysym in ("1", "2", "3", "4", "5", "6", "7", "8", "9"))


class TkInputHandler:
    """Translates Tkinter UI events into terminal session interactions."""

    def __init__(self, session: TerminalSession) -> None:
        self.session = session
        self.selection = Selection()

    def pixel_to_cell(self, x: int, y: int, cell_w: int, cell_h: int) -> tuple[int, int]:
        """Convert pixel coordinates to zero-indexed character column and row."""
        col = max(0, min(self.session.cols - 1, x // cell_w))
        row = max(0, min(self.session.rows - 1, y // cell_h))
        return col, row

    def on_button_1_press(
        self, event: tk.Event, cell_w: int, cell_h: int, canvas: tk.Canvas
    ) -> None:
        """Handle primary mouse button down."""
        col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        if self.session.parser.mouse_tracking:
            self.session.send_mouse(0, col, row, release=False)
            return

        # OSC 8 Hyperlink click handling (with secure scheme allowlist)
        cell = self.session.screen.get_visible_row(row)[col]
        if cell.url and (event.state & 0x4 or (sys.platform == "darwin" and event.state & 0x8)):
            parsed = urllib.parse.urlparse(cell.url)
            if parsed.scheme in ("http", "https"):
                webbrowser.open(cell.url)
            return

        self.selection = Selection(
            active=True,
            start_col=col,
            start_row=row,
            end_col=col,
            end_row=row,
        )
        canvas.focus_set()

    def on_button_1_motion(
        self, event: tk.Event, cell_w: int, cell_h: int
    ) -> None:
        """Handle mouse drag selection or button-event tracking."""
        if self.session.parser.mouse_tracking:
            if getattr(self.session.parser, "mouse_button_motion", False) or getattr(
                self.session.parser, "mouse_all_motion", False
            ):
                col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
                self.session.send_mouse(32, col, row, release=False)
            return
        if not self.selection.active:
            return
        col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        self.selection.end_col = col
        self.selection.end_row = row

    def on_button_1_release(
        self, event: tk.Event, cell_w: int, cell_h: int, canvas: tk.Canvas
    ) -> None:
        """Handle mouse button release."""
        col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        if self.session.parser.mouse_tracking:
            self.session.send_mouse(0, col, row, release=True)
            return
        if self.selection.is_empty():
            self.selection.active = False
            canvas.delete("selection_box")

    def on_double_click(
        self, event: tk.Event, cell_w: int, cell_h: int
    ) -> None:
        """Expand selection to word under pointer."""
        if self.session.parser.mouse_tracking:
            return
        col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        row_cells = self.session.screen.get_visible_row(row)

        start_col = col
        while start_col > 0 and row_cells[start_col - 1].char not in WORD_DELIMITERS:
            start_col -= 1

        end_col = col
        while end_col < self.session.cols - 1 and row_cells[end_col + 1].char not in WORD_DELIMITERS:
            end_col += 1

        self.selection = Selection(
            active=True,
            start_col=start_col,
            start_row=row,
            end_col=end_col,
            end_row=row,
        )

    def on_triple_click(
        self, event: tk.Event, cell_w: int, cell_h: int
    ) -> None:
        """Select entire line under pointer."""
        if self.session.parser.mouse_tracking:
            return
        _col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        self.selection = Selection(
            active=True,
            start_col=0,
            start_row=row,
            end_col=self.session.cols - 1,
            end_row=row,
        )

    def on_pointer_motion(
        self, event: tk.Event, cell_w: int, cell_h: int, canvas: tk.Canvas
    ) -> None:
        """Update cursor shape for OSC 8 hyperlinks or report motion in any-event tracking."""
        col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
        if getattr(self.session.parser, "mouse_all_motion", False):
            self.session.send_mouse(35, col, row, release=False)
            return

        cell = self.session.screen.get_visible_row(row)[col]
        if cell.url:
            canvas.config(cursor="hand2")
        else:
            canvas.config(cursor="xterm")

    def on_mouse_scroll(
        self, delta: int, event: tk.Event | None, cell_w: int, cell_h: int, canvas: tk.Canvas
    ) -> None:
        """Scroll view or send mouse wheel reporting."""
        if self.session.parser.mouse_tracking and event is not None:
            col, row = self.pixel_to_cell(event.x, event.y, cell_w, cell_h)
            btn = 64 if delta < 0 else 65
            self.session.send_mouse(btn, col, row, release=False)
            return

        canvas.delete("selection_box")
        self.selection.active = False
        self.session.screen.scroll_view(-delta)

    def on_key_press(self, event: tk.Event, canvas: tk.Canvas) -> str:
        """Forward key press event to terminal session."""
        if is_application_shortcut(event):
            return ""

        self.session.screen.reset_view()

        if event.keysym == "Escape" and self.selection.active:
            self.selection.active = False
            canvas.delete("selection_box")
            return "break"

        # Shift+PageUp / Shift+PageDown for view scroll
        if event.keysym == "Prior" and (event.state & 0x1):
            self.session.screen.scroll_view(self.session.rows // 2)
            return "break"
        if event.keysym == "Next" and (event.state & 0x1):
            self.session.screen.scroll_view(-(self.session.rows // 2))
            return "break"

        self.session.send_key(keysym=event.keysym, state=event.state, char=event.char)
        return "break"
