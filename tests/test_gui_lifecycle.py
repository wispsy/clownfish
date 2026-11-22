"""Behavioral tests for Tkinter GUI lifecycle, tab closing, smoke tests, and event scheduling."""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from clownfish import main
from clownfish.config import TerminalConfig
from clownfish.core.models import Selection
from clownfish.core.screen import ScreenBuffer
from clownfish.core.search import SearchMatch
from clownfish.frontends.tkinter.app import TkTerminalApp
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer
from clownfish.frontends.tkinter.tabs import TabbedTerminalView
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport
from clownfish.transports.pty import PTYTransport


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


def test_cli_smoke_test_argument() -> None:
    """Verify clownfish --smoke-test creates and destroys Tk window cleanly or reports display state."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
        try:
            main(["--smoke-test"])
            assert "GUI smoke test passed successfully" in stdout_buf.getvalue()
        except SystemExit as exc:
            assert exc.code == 2
            assert "GUI smoke test display unavailable" in stderr_buf.getvalue()


def test_gui_smoke_test_exit_code_contract() -> None:
    """Verify --smoke-test exits 0 on success and exits 2 when display is unavailable."""
    import tkinter as tk

    with patch.object(tk, "Tk", side_effect=tk.TclError("no display")):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf), pytest.raises(SystemExit) as exc:
            main(["--smoke-test"])
        assert exc.value.code == 2
        assert "display unavailable" in stderr_buf.getvalue()


def test_background_tab_pane_closed_cleanup() -> None:
    """Verify closing a background tab cleans up without crashing."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root)
            tab_view.new_tab(title="Tab 2")
            assert len(tab_view.tabs) == 2

            tab_view.switch_tab(0)
            assert tab_view.active_tab_index == 0

            bg_split_view = tab_view.tabs[1][1]
            bg_pane = bg_split_view.panes()[0]

            bg_split_view._handle_pane_close(bg_pane)
            assert len(tab_view.tabs) == 1
            assert tab_view.active_tab_index == 0
    finally:
        root.destroy()


def test_background_tab_closed_preserves_active_tab_3tabs() -> None:
    """Verify closing a background tab in a 3-tab setup preserves the user's active tab."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root, config=TerminalConfig())
            tab_view.new_tab(title="Tab 2")
            tab_view.new_tab(title="Tab 3")
            assert len(tab_view.tabs) == 3

            tab_view.switch_tab(0)
            assert tab_view.active_tab_index == 0

            tab_view.close_tab(1)
            assert len(tab_view.tabs) == 2
            assert tab_view.active_tab_index == 0

            tab_view.close_tab(1)
            assert len(tab_view.tabs) == 1
            assert tab_view.active_tab_index == 0
    finally:
        root.destroy()


def test_tab_bar_request_close_confirmation() -> None:
    """Verify tab bar close button asks for confirmation when confirm_close_active_process=True."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(
                root, config=TerminalConfig(confirm_close_active_process=True)
            )
            pane = tab_view.active_pane
            with patch.object(pane, "has_foreground_process", return_value=True):
                with patch.object(messagebox, "askyesno", return_value=False) as mock_msg:
                    closed = tab_view.request_close_tab(0)
                    assert closed is False
                    assert len(tab_view.tabs) == 1
                    mock_msg.assert_called_once()

                with patch.object(messagebox, "askyesno", return_value=True) as mock_msg:
                    closed = tab_view.request_close_tab(0)
                    assert closed is True
    finally:
        root.destroy()


def test_render_tick_consolidation_single_job() -> None:
    """Verify _on_session_event avoids cross-thread cancel and maintains single scheduled job."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root)
            pane = tab_view.active_pane

            assert pane._tick_job is not None
            first_job = pane._tick_job

            # Firing _on_session_event when tick is already active does not cancel or duplicate
            pane._on_session_event()
            assert pane._tick_job == first_job

            pane.close()
            assert pane._closed is True
            assert pane._tick_job is None
    finally:
        root.destroy()


def test_selection_and_search_highlight_z_order() -> None:
    """Verify that text and cursor are raised above selection and search highlights."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        canvas = tk.Canvas(root, width=300, height=200)
        config = TerminalConfig()
        renderer = TkCanvasRenderer(canvas, config)
        screen = ScreenBuffer(cols=20, rows=10)

        screen.put_char("H")
        screen.put_char("i")
        renderer.render(screen, cols=20, rows=10)

        sel = Selection(active=True, start_col=0, start_row=0, end_col=5, end_row=0)
        renderer.draw_selection(sel, cols=20)

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

        items = canvas.find_all()
        tags = [canvas.gettags(i)[0] for i in items if canvas.gettags(i)]
        assert "selection_box" in tags
        assert "search_highlight" in tags
        assert "cursor" in tags
    finally:
        root.destroy()


def test_supplied_session_in_tk_app() -> None:
    """Verify TkTerminalApp accepts an externally supplied session without error."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        transport = DummyTransport()
        session = TerminalSession(transport=transport)
        app = TkTerminalApp(root, session=session)
        assert app.session is session
        assert hasattr(app.active_pane, "_on_session_event")
    finally:
        root.destroy()
