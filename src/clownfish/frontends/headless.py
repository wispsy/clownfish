"""Headless terminal frontend for non-GUI execution, automation, and testing."""

from __future__ import annotations

import re
import time
from types import TracebackType
from typing import Self

from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport


class HeadlessTerminal:
    """Programmatic headless terminal interface wrapping TerminalSession.

    Provides a clean, dependency-free API to run shell or SSH sessions, send keystrokes,
    and inspect terminal screen content without any graphical window (Tkinter).
    """

    def __init__(
        self,
        cols: int = 80,
        rows: int = 24,
        max_scrollback: int = 10_000,
        transport: Transport | None = None,
        cwd: str | None = None,
        title: str = "clownfish-headless",
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.session = TerminalSession(
            cols=cols,
            rows=rows,
            max_scrollback=max_scrollback,
            transport=transport,
            title=title,
            auto_drain=True,
            cwd=cwd,
        )

    def start(self) -> Self:
        """Start the session transport."""
        self.session.start()
        return self

    def drain(self, max_bytes: int = 512_000) -> bool:
        """Drain any pending bytes and events from the transport."""
        return self.session.drain_events(max_bytes=max_bytes)

    def send_input(self, text: str) -> None:
        """Send plain text or shell commands into the terminal transport."""
        self.session.write(text.encode("utf-8"))

    def send_key(self, keysym: str, state: int = 0, char: str = "") -> bool:
        """Send a formatted keystroke event into the session."""
        return self.session.send_key(keysym=keysym, state=state, char=char)

    @property
    def cursor_position(self) -> tuple[int, int]:
        """Return the current cursor (col, row) coordinates (0-indexed)."""
        return self.session.screen.cursor_x, self.session.screen.cursor_y

    def get_line(self, row: int, rstrip: bool = True) -> str:
        """Return the text content of a single visible row."""
        if not (0 <= row < self.session.rows):
            raise IndexError(f"Row {row} is out of bounds (0..{self.session.rows - 1})")
        cells = self.session.screen.get_visible_row(row)
        line = "".join(cell.char for cell in cells if cell.width != 0)
        return line.rstrip() if rstrip else line

    def get_text(
        self,
        start_row: int = 0,
        end_row: int | None = None,
        rstrip: bool = True,
        include_scrollback: bool = False,
    ) -> str:
        """Return visible screen lines as a newline-delimited string.

        If `include_scrollback` is True, prepends all saved scrollback lines.
        """
        self.drain()
        lines: list[str] = []

        if include_scrollback:
            for row in self.session.screen.scrollback:
                line_text = "".join(cell.char for cell in row.cells if cell.width != 0)
                lines.append(line_text.rstrip() if rstrip else line_text)

        last_row = self.session.rows if end_row is None else min(self.session.rows, end_row)
        for r in range(start_row, last_row):
            lines.append(self.get_line(r, rstrip=rstrip))

        return "\n".join(lines)

    def wait_for_text(
        self,
        pattern: str | re.Pattern[str],
        timeout: float = 5.0,
        interval: float = 0.05,
        include_scrollback: bool = False,
    ) -> bool:
        """Poll terminal output until `pattern` matches or `timeout` expires.

        `pattern` may be a plain string substring or a compiled regex.
        Returns True if matched, False on timeout.
        """
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            self.drain()
            current_text = self.get_text(include_scrollback=include_scrollback)
            if regex.search(current_text):
                return True
            time.sleep(interval)

        # Final drain check
        self.drain()
        return bool(regex.search(self.get_text(include_scrollback=include_scrollback)))

    def wait_for_prompt(self, timeout: float = 5.0, interval: float = 0.05) -> bool:
        """Wait until an OSC 133 semantic prompt mark or common prompt symbol appears."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.drain()
            if self.session.screen.prompt_markers:
                return True
            # Also check text for common prompt terminators ($ or % or #)
            screen_text = self.get_text()
            if re.search(r"[$%#>]\s*$", screen_text, re.MULTILINE):
                return True
            time.sleep(interval)
        return bool(self.session.screen.prompt_markers)

    def is_alive(self) -> bool:
        """Return True if the underlying session transport process is active."""
        return self.session.is_alive()

    def close(self) -> None:
        """Cleanly close the session and its transport."""
        self.session.close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
