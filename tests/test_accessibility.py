"""Tests for accessible text interface bridge and screen reader integration."""

from __future__ import annotations

from clownfish.core.accessibility import AccessibleTextBridge
from clownfish.core.models import Cell, Style
from clownfish.core.screen import ScreenBuffer


def test_a11y_bridge_extract_line_text() -> None:
    screen = ScreenBuffer(cols=20, rows=5)
    row = screen.grid[0]
    for i, ch in enumerate("hello world"):
        row[i] = Cell(char=ch, style=Style())

    bridge = AccessibleTextBridge()
    line_0 = bridge.get_line_text(screen, 0)
    assert line_0 == "hello world"

    empty_line = bridge.get_line_text(screen, 1)
    assert empty_line == ""


def test_a11y_bridge_current_line_and_status() -> None:
    screen = ScreenBuffer(cols=30, rows=5)
    screen.cursor_x = 5
    screen.cursor_y = 2
    row = screen.grid[2]
    for i, ch in enumerate("status line test"):
        row[i] = Cell(char=ch, style=Style())

    bridge = AccessibleTextBridge(enabled=True)
    curr_line = bridge.get_current_line_text(screen)
    assert curr_line == "status line test"

    status = bridge.get_status_description(screen)
    assert "Line 3, Column 6" in status
    assert "status line test" in status


def test_a11y_bridge_cursor_tracking_and_announcement() -> None:
    screen = ScreenBuffer(cols=20, rows=5)
    announcements: list[str] = []

    bridge = AccessibleTextBridge(
        enabled=True,
        on_announcement=lambda msg: announcements.append(msg),
    )

    # Initial state
    screen.cursor_x = 0
    screen.cursor_y = 0
    bridge.update_cursor_state(screen)
    assert len(announcements) == 1
    assert announcements[0] == "blank"

    # Move cursor on same row
    screen.cursor_x = 4
    bridge.update_cursor_state(screen)
    assert len(announcements) == 1  # didn't change row

    # Move cursor to new row with text
    screen.cursor_y = 1
    row = screen.grid[1]
    for i, ch in enumerate("new command"):
        row[i] = Cell(char=ch, style=Style())

    bridge.update_cursor_state(screen)
    assert len(announcements) == 2
    assert "new command" in announcements[1]


def test_a11y_bridge_disabled_suppresses_announcement() -> None:
    screen = ScreenBuffer(cols=20, rows=5)
    announcements: list[str] = []

    bridge = AccessibleTextBridge(
        enabled=False,
        on_announcement=lambda msg: announcements.append(msg),
    )

    screen.cursor_y = 2
    bridge.update_cursor_state(screen)
    assert len(announcements) == 0

    # Explicit announce still works if caller requests it
    bridge.announce("Manual prompt announcement")
    assert announcements == ["Manual prompt announcement"]
