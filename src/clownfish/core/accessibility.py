"""Accessibility interfaces, screen reader bridge, and text announcement hooks."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clownfish.core.screen import ScreenBuffer


class AccessibleTextBridge:
    """Provides structured text access, line inspection, and speech hooks for assistive tech."""

    def __init__(
        self,
        on_announcement: Callable[[str], None] | None = None,
        enabled: bool = False,
    ) -> None:
        self.enabled = enabled
        self.on_announcement = on_announcement
        self._last_cursor_row: int = -1
        self._last_cursor_col: int = -1
        self._last_line_content: str = ""

    def get_line_text(self, screen: ScreenBuffer, row: int) -> str:
        """Extract plain text string for given terminal row."""
        if not (0 <= row < screen.rows):
            return ""
        row_cells = screen.get_visible_row(row)
        return "".join(c.char for c in row_cells if c.width != 0).rstrip()

    def get_current_line_text(self, screen: ScreenBuffer) -> str:
        """Return the text content of the row currently containing the cursor."""
        return self.get_line_text(screen, screen.cursor_y)

    def get_status_description(self, screen: ScreenBuffer) -> str:
        """Return a human-readable status description for screen readers."""
        line = self.get_current_line_text(screen)
        offset_desc = (
            f", scrollback offset {screen.scroll_offset}" if screen.scroll_offset > 0 else ""
        )
        return f"Line {screen.cursor_y + 1}, Column {screen.cursor_x + 1}{offset_desc}: {line}"

    def update_cursor_state(self, screen: ScreenBuffer) -> str | None:
        """Check cursor row and line changes; return text to announce if changed."""
        if not self.enabled:
            return None

        current_row = screen.cursor_y
        current_col = screen.cursor_x
        current_line = self.get_current_line_text(screen)

        announcement: str | None = None
        if current_row != self._last_cursor_row:
            # Announce whole line when navigating between lines
            announcement = current_line or "blank"
            self._last_cursor_row = current_row
            self._last_cursor_col = current_col
            self._last_line_content = current_line
        elif current_line != self._last_line_content:
            # Content changed on same line (e.g. typing or output)
            self._last_line_content = current_line

        if announcement and self.on_announcement:
            self.on_announcement(announcement)

        return announcement

    def announce(self, text: str) -> None:
        """Send an explicit announcement to screen reader / speech."""
        if not text:
            return
        if self.on_announcement:
            self.on_announcement(text)
        elif self.enabled and sys.platform == "darwin":
            # Direct non-blocking macOS TTS fallback
            try:
                subprocess.Popen(
                    ["say", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except OSError:
                pass
