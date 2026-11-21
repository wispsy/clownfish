"""Comprehensive tests for Milestone 0.6.1 review corrections and stabilization."""

from __future__ import annotations

import io
import json
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

import clownfish
from clownfish import HeadlessTerminal, main
from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.app import TkTerminalApp
from clownfish.frontends.tkinter.tabs import TabbedTerminalView
from clownfish.session.persistence import (
    PaneState,
    SessionState,
    SplitNodeState,
    TabState,
)
from clownfish.transports.pty import PTYTransport
from clownfish.transports.ssh import SSHTransport

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_bump_061() -> None:
    """Verify package version is at least 0.6.1."""
    assert clownfish.__version__ >= "0.6.1"


def test_pty_write_backpressure_and_saturation() -> None:
    """Verify PTYTransport applies backpressure and raises BufferError on saturation timeout."""
    transport = PTYTransport(cols=80, rows=24)
    transport._running = True
    transport.master_fd = 999  # Mock valid descriptor

    # Reduce queue limit for deterministic test
    transport.MAX_WRITE_QUEUE_CHUNKS = 3

    # Enqueue up to limit
    transport.write(b"chunk-1")
    transport.write(b"chunk-2")
    transport.write(b"chunk-3")
    assert len(transport._write_queue) == 3

    # Writing when saturated should timeout and raise BufferError
    with pytest.raises(BufferError, match="saturated"):
        transport.write(b"chunk-overflow", timeout=0.05)

    # Draining a chunk should notify condition and allow subsequent write
    def pop_chunk_later() -> None:
        import time

        time.sleep(0.05)
        with transport._write_cv:
            transport._write_queue.popleft()
            transport._write_cv.notify()

    t = threading.Thread(target=pop_chunk_later)
    t.start()

    transport.write(b"chunk-4", timeout=0.5)
    t.join()
    assert b"chunk-4" in transport._write_queue


def test_headless_scrollback_iteration_fix() -> None:
    """Verify get_text(include_scrollback=True) works with real scrollback rows."""
    with HeadlessTerminal(cols=40, rows=4) as term:
        # Feed enough text to push rows into scrollback
        for i in range(10):
            term.session.feed_text(f"line_{i}\r\n")

        # Must have scrollback rows
        assert len(term.session.screen.scrollback) > 0

        # This previously raised AttributeError: 'Row' object has no attribute 'cells'
        full_text = term.get_text(include_scrollback=True)
        assert isinstance(full_text, str)
        assert "line_0" in full_text
        assert "line_9" in full_text


def test_headless_fresh_prompt_wait_sequence() -> None:
    """Verify wait_for_prompt correctly tracks sequential prompts without premature returns."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        # Initial state has no markers
        assert len(term.session.screen.prompt_markers) == 0

        # Simulate first shell prompt (OSC 133;A)
        term.session.feed_text("\x1b]133;A\x07user@host:~$ ")
        assert term.wait_for_prompt(timeout=0.5) is True

        # Second wait immediately without new prompt should timeout
        assert term.wait_for_prompt(timeout=0.05) is False

        # Simulate command execution and second prompt
        term.session.feed_text("ls\r\n\x1b]133;C\x07output\r\n\x1b]133;D;0\x07\x1b]133;A\x07user@host:~$ ")
        assert term.wait_for_prompt(timeout=0.5) is True


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


def test_cli_command_execution_headless() -> None:
    """Verify clownfish -c executes command and streams output."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["-c", "echo CLOWNFISH_CLI_C_TEST"])
    output = stdout_buf.getvalue()
    assert "CLOWNFISH_CLI_C_TEST" in output


def test_session_state_atomic_save_and_recovery() -> None:
    """Verify atomic file saving and corrupted schema recovery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = Path(tmpdir) / "session_state.json"

        state = SessionState(
            version=1,
            active_tab_index=0,
            tabs=[TabState(title="Primary", root=SplitNodeState(is_leaf=True, pane=PaneState(cwd="/tmp")))],
        )
        saved = state.save(save_path)
        assert saved.exists()

        # Load valid state
        loaded = SessionState.load(save_path)
        assert loaded is not None
        assert len(loaded.tabs) == 1
        assert loaded.tabs[0].title == "Primary"

        # Corrupt file with malformed JSON
        save_path.write_text("{malformed json", encoding="utf-8")
        assert SessionState.load(save_path) is None

        # Corrupt file with invalid types in schema
        save_path.write_text(json.dumps({"version": "bad", "tabs": "not a list"}), encoding="utf-8")
        recovered = SessionState.load(save_path)
        assert recovered is not None
        assert len(recovered.tabs) == 1  # Recovers default tab


def test_ssh_initial_tab_no_local_shell_leak() -> None:
    """Verify launching an SSH session does not spawn an orphaned local shell."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            ssh_transport = SSHTransport(host="example.com", port=22)
            from clownfish.session.session import TerminalSession

            ssh_session = TerminalSession(transport=ssh_transport, auto_drain=False)

            # Create app with explicit SSH session
            app = TkTerminalApp(root, session=ssh_session, config=TerminalConfig())

            # Check that active pane uses the supplied SSH session
            assert app.tab_view.active_pane is not None
            assert app.tab_view.active_pane.session is ssh_session
            assert app.tab_view.active_pane.session.transport is ssh_transport
            # Verify only 1 tab exists
            assert len(app.tab_view.tabs) == 1
    finally:
        root.destroy()


def test_background_tab_pane_closed_cleanup() -> None:
    """Verify closing a pane in a background tab removes that tab without affecting active tab."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root, config=TerminalConfig())

            # Create second tab
            tab_view.new_tab(title="Tab 2")
            assert len(tab_view.tabs) == 2
            assert tab_view.active_tab_index == 1

            # Switch back to Tab 0 as active
            tab_view.switch_tab(0)
            assert tab_view.active_tab_index == 0

            # Background tab is Tab 1
            bg_split_view = tab_view.tabs[1][1]
            bg_pane = bg_split_view.panes()[0]

            # Simulate background pane close
            bg_split_view._handle_pane_close(bg_pane)

            # Tab 1 should now be closed, Tab 0 remains active
            assert len(tab_view.tabs) == 1
            assert tab_view.active_tab_index == 0
            assert tab_view.tabs[0][0] == "Terminal 1"
    finally:
        root.destroy()


def test_auto_reconnect_ssh_setting() -> None:
    """Verify auto_reconnect_ssh=False does not reconnect remote SSH host on restore."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    ssh_node = SplitNodeState(
        is_leaf=True,
        pane=PaneState(
            cwd=None,
            title="remote-server",
            ssh={"host": "remote.test", "port": 22},
        ),
    )

    from clownfish.frontends.tkinter.split import SplitView

    try:
        # Config with auto_reconnect_ssh=False
        config_no_reconnect = TerminalConfig(auto_reconnect_ssh=False)
        with patch.object(PTYTransport, "start"):
            sv = SplitView(root, config=config_no_reconnect, create_initial_pane=False)
            sv.load_state(ssh_node)
            assert len(sv.panes()) == 1
            pane = sv.panes()[0]
            # Session transport should not be SSHTransport
            assert not isinstance(pane.session.transport, SSHTransport)
    finally:
        root.destroy()


def test_homebrew_formula_dependencies_and_smoke_test() -> None:
    """Verify Formula includes python-tk dependency and GUI smoke test command."""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.publish_homebrew import render_formula

    formula_str = render_formula("0.6.2", "dummy_sha256")
    assert 'depends_on "python@3.14"' in formula_str
    assert 'depends_on "python-tk@3.14"' in formula_str
    assert 'libexec/"bin/python"' in formula_str
    assert "import tkinter; import clownfish" in formula_str
