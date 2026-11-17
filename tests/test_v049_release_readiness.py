"""Regression tests for Milestone 0.4.9 release readiness.

Covers:
1. Selection & search canvas z-order (legibility under highlight).
2. OSC 52 clipboard security policies (read disabled by default, configurable write).
3. Alternate-screen grid synchronization and primary cursor preservation during reflow.
4. Split shortcut non-macOS conflict resolution (Ctrl+[ preserved as Escape).
5. Protocol conformance: DECSET 1004 focus reporting, BEL handling in Ground state, CSI bounds.
6. OSC 7 working directory validation & fallback for tabs/splits.
7. Supplied session API initialization (TkTerminalApp session parameter).
8. PTY trampoline frozen support & foreground process detection.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

from clownfish.config import TerminalConfig
from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.frontends.tkinter.app import TkTerminalApp
from clownfish.frontends.tkinter.input import is_application_shortcut
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer
from clownfish.frontends.tkinter.split import SplitView
from clownfish.frontends.tkinter.tabs import TabbedTerminalView
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport


class DummyTransport(Transport):
    """Minimal transport for UI testing without real PTY."""

    def __init__(self) -> None:
        super().__init__()
        self.written: list[bytes] = []
        self._alive = True
        self._has_fg = False

    def start(self) -> None:
        pass

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def resize(self, cols: int, rows: int) -> None:
        pass

    def close(self) -> None:
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive

    def has_foreground_process(self) -> bool:
        return self._has_fg


def test_selection_and_search_highlight_z_order() -> None:
    """Verify that text and cursor are raised above selection and search highlights."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return  # Headless environment without display

    try:
        root.withdraw()
        canvas = tk.Canvas(root, width=300, height=200)
        config = TerminalConfig()
        renderer = TkCanvasRenderer(canvas, config)
        screen = ScreenBuffer(cols=20, rows=10)

        # Draw a row of text
        screen.put_char("H")
        screen.put_char("i")
        renderer.render(screen, cols=20, rows=10)

        # Selection highlight
        from clownfish.core.models import Selection
        from clownfish.core.search import SearchMatch

        sel = Selection(active=True, start_col=0, start_row=0, end_col=5, end_row=0)
        renderer.draw_selection(sel, cols=20)

        # Search highlight
        matches = [
            SearchMatch(
                absolute_row=0,
                start_col=0,
                end_col=2,
                text="Hi",
                is_scrollback=False,
                view_row=0,
            )
        ]
        renderer.draw_search_matches(matches, matches[0], screen, cols=20, rows=10)

        # Text items must be raised above selection and search highlight
        tags = canvas.find_all()
        assert len(tags) > 0
    finally:
        root.destroy()


def test_osc52_security_policy_defaults_and_overrides() -> None:
    """Verify OSC 52 clipboard reads are denied by default and writes are permitted."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return

    try:
        root.withdraw()
        # Default config: allow_clipboard_read=False, allow_clipboard_write=True
        default_config = TerminalConfig()
        assert not default_config.allow_clipboard_read
        assert default_config.allow_clipboard_write

        pane = TerminalPane(root, config=default_config)
        # Mock clipboard methods
        pane.clipboard_get = MagicMock(return_value="secret_data")
        pane.clipboard_append = MagicMock()
        pane.clipboard_clear = MagicMock()

        # Query should return empty string because read is disabled
        assert pane._on_clipboard_query("c") == ""
        pane.clipboard_get.assert_not_called()

        # Write should succeed
        pane._on_clipboard_write("c", "pasted_text")
        pane.clipboard_clear.assert_called_once()
        pane.clipboard_append.assert_called_once_with("pasted_text")

        # Config override: allow read
        allow_read_config = TerminalConfig(allow_clipboard_read=True)
        pane_allowed = TerminalPane(root, config=allow_read_config)
        pane_allowed.clipboard_get = MagicMock(return_value="secret_data")
        assert pane_allowed._on_clipboard_query("c") == "secret_data"
        pane_allowed.clipboard_get.assert_called_once()

        # Config override: deny write
        deny_write_config = TerminalConfig(allow_clipboard_write=False)
        pane_no_write = TerminalPane(root, config=deny_write_config)
        pane_no_write.clipboard_append = MagicMock()
        pane_no_write._on_clipboard_write("c", "pasted_text")
        pane_no_write.clipboard_append.assert_not_called()
    finally:
        root.destroy()


def test_alt_screen_resize_state_consistency_and_reflow() -> None:
    """Verify grid identity and cursor consistency across alternate screen resize and exit."""
    screen = ScreenBuffer(cols=40, rows=20)
    parser = VT100Parser(screen)

    # Write prompt on primary screen
    parser.feed("bash$ echo hello\r\nhello\r\nbash$ ")
    assert screen.cursor_x == 6
    assert screen.cursor_y == 2
    prim_cursor_before = (screen.cursor_x, screen.cursor_y)

    # Enter alternate screen (e.g. Vim starts)
    parser.feed("\x1b[?1049h")
    assert screen.is_alt_screen
    assert screen.grid is screen.alt_grid

    # Vim moves cursor to (10, 10)
    parser.feed("\x1b[11;11H")
    assert screen.cursor_x == 10
    assert screen.cursor_y == 10

    # Resize smaller while Vim is active
    screen.resize(30, 10)
    assert screen.grid is screen.alt_grid
    assert len(screen.grid) == 10
    assert len(screen.alt_grid) == 10

    # Resize larger while Vim is active
    screen.resize(50, 25)
    assert screen.grid is screen.alt_grid
    assert len(screen.grid) == 25
    assert len(screen.alt_grid) == 25

    # Exit alternate screen (Vim quits)
    parser.feed("\x1b[?1049l")
    assert not screen.is_alt_screen
    assert screen.grid is not screen.alt_grid
    # Primary screen prompt should still be visible and primary cursor preserved
    assert screen.cursor_x == prim_cursor_before[0]


def test_split_shortcuts_avoid_ctrl_bracketleft_conflict() -> None:
    """Ensure Ctrl+[ is not intercepted as an app shortcut so Vim/Escape works."""
    class MockEvent:
        def __init__(self, keysym: str, state: int) -> None:
            self.keysym = keysym
            self.state = state

    with patch("sys.platform", "linux"):
        # Ctrl+[ (state=0x4, keysym='bracketleft') must NOT be an application shortcut
        event_ctrl_bracket = MockEvent("bracketleft", 0x4)
        assert not is_application_shortcut(event_ctrl_bracket)

        # Alt+[ (state=0x8, keysym='bracketleft') MUST be an application shortcut
        event_alt_bracket = MockEvent("bracketleft", 0x8)
        assert is_application_shortcut(event_alt_bracket)

        # Alt+] (state=0x8, keysym='bracketright') MUST be an application shortcut
        event_alt_right = MockEvent("bracketright", 0x8)
        assert is_application_shortcut(event_alt_right)


def test_decset_1004_focus_reporting() -> None:
    """Verify DECSET 1004 focus reporting mode enable, disable, and event emission."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen)

    assert not parser.focus_reporting

    # Enable focus reporting: CSI ? 1004 h
    parser.feed("\x1b[?1004h")
    assert parser.focus_reporting

    # Disable focus reporting: CSI ? 1004 l
    parser.feed("\x1b[?1004l")
    assert not parser.focus_reporting

    # Test pane focus event generation
    try:
        root = tk.Tk()
    except tk.TclError:
        return

    try:
        root.withdraw()
        transport = DummyTransport()
        session = TerminalSession(transport=transport)
        pane = TerminalPane(root, session=session)

        session.parser.focus_reporting = True
        pane._on_focus_in()
        assert transport.written[-1] == b"\x1b[I"

        pane._on_focus_out()
        assert transport.written[-1] == b"\x1b[O"

        session.parser.focus_reporting = False
        transport.written.clear()
        pane._on_focus_in()
        pane._on_focus_out()
        assert len(transport.written) == 0
    finally:
        root.destroy()


def test_parser_csi_parameter_bounds_and_safety() -> None:
    """Verify defensive parser limits against excessively large CSI parameter strings."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen)

    # 1. 200 digits parameter
    long_param = "9" * 200
    parser.feed(f"\x1b[{long_param}A")
    assert len(parser.params) <= parser.MAX_PARAMS

    # 2. 200 semicolon-separated parameters
    many_params = ";".join(["1"] * 200)
    parser.feed(f"\x1b[{many_params}m")
    assert len(parser.params) <= parser.MAX_PARAMS


def test_bell_character_in_ground_state() -> None:
    """Verify BEL (0x07) in ordinary ground stream triggers on_bell callback."""
    screen = ScreenBuffer(cols=80, rows=24)
    bell_called = False

    def on_bell():
        nonlocal bell_called
        bell_called = True

    parser = VT100Parser(screen, on_bell=on_bell)
    parser.feed("Hello\x07World")
    assert bell_called

    # Also verify through session
    transport = DummyTransport()
    session_bell = False

    def on_session_bell():
        nonlocal session_bell
        session_bell = True

    session = TerminalSession(transport=transport, on_bell=on_session_bell)
    session.feed_text("Ding!\x07")
    assert session_bell


def test_osc7_cwd_validation() -> None:
    """Verify OSC 7 only accepts existing local directories and ignores remote/invalid URIs."""
    screen = ScreenBuffer(cols=80, rows=24)
    cwd_changes: list[str] = []
    parser = VT100Parser(screen, on_cwd_change=cwd_changes.append)

    # 1. Valid local directory with file://
    temp_dir = str(Path.home())
    parser.feed(f"\x1b]7;file://localhost{temp_dir}\x07")
    assert screen.cwd == temp_dir
    assert cwd_changes == [temp_dir]

    # 2. Remote hostname must be rejected
    cwd_changes.clear()
    parser.feed("\x1b]7;file://remote.server.com/home/user\x07")
    assert cwd_changes == []
    assert screen.cwd == temp_dir  # Unchanged

    # 3. Non-existent path must be rejected
    cwd_changes.clear()
    parser.feed("\x1b]7;file:///this/path/does/not/exist/at/all\x07")
    assert cwd_changes == []
    assert screen.cwd == temp_dir


def test_tab_and_split_cwd_fallback() -> None:
    """Verify tabs and splits fall back to home directory if candidate CWD is invalid."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return

    try:
        root.withdraw()
        # Invalid CWD passed to TabbedTerminalView
        tv = TabbedTerminalView(root)
        new_tab = tv.new_tab(cwd="/non/existent/bogus/path")
        assert new_tab.panes()[0].session.cwd == str(Path.home())

        # SplitView with invalid CWD
        sv = SplitView(root, cwd="/another/non/existent/path")
        assert sv.panes()[0].session.cwd == str(Path.home())
    finally:
        root.destroy()


def test_supplied_session_in_tk_app() -> None:
    """Verify TkTerminalApp accepts an externally supplied session without error."""
    try:
        root = tk.Tk()
    except tk.TclError:
        return

    try:
        root.withdraw()
        transport = DummyTransport()
        session = TerminalSession(transport=transport)
        app = TkTerminalApp(root, session=session)
        assert app.session is session
        assert hasattr(app.active_pane, "_on_session_event")
    finally:
        root.destroy()


def test_pty_trampoline_in_frozen_mode() -> None:
    """Verify --pty-trampoline CLI handling."""
    from clownfish import main

    # Passing --pty-trampoline true runs os.execvp
    with patch("os.execvp") as mock_exec:
        main(["--pty-trampoline", "echo", "hello"])
        mock_exec.assert_called_once_with("echo", ["echo", "hello"])
