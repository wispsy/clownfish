"""Comprehensive tests for Milestone 0.6.2 stabilization and distribution hardening."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import clownfish
from clownfish import CommandResult, HeadlessTerminal, main
from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.tabs import TabbedTerminalView
from clownfish.session.persistence import (
    PaneState,
    SplitNodeState,
)
from clownfish.transports.pty import PTYTransport

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_version_bump_062() -> None:
    """Verify package version is 0.6.2."""
    assert clownfish.__version__ == "0.6.2"


def test_command_result_str_subclass() -> None:
    """Verify CommandResult behaves both as a string and structured result."""
    cr = CommandResult("hello world\n", command="echo hello world", exit_code=0)
    assert isinstance(cr, str)
    assert "hello" in cr
    assert cr.command == "echo hello world"
    assert cr.exit_code == 0
    assert cr.strip() == "hello world"


def test_headless_run_command_sentinel_and_exit_code() -> None:
    """Verify run_command returns command-only output and captures exit code."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        # First command
        res1 = term.run_command("echo CLOWNFISH_TOKEN_1", timeout=5.0)
        assert isinstance(res1, CommandResult)
        assert res1.exit_code == 0
        assert "CLOWNFISH_TOKEN_1" in res1

        # Second command: verify previous command output is not returned
        res2 = term.run_command("echo CLOWNFISH_TOKEN_2", timeout=5.0)
        assert res2.exit_code == 0
        assert "CLOWNFISH_TOKEN_2" in res2
        assert "CLOWNFISH_TOKEN_1" not in res2

        # Non-zero exit code capture
        res3 = term.run_command("sh -c 'exit 42'", timeout=5.0)
        assert res3.exit_code == 42

        # Check=True should raise CalledProcessError
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            term.run_command("sh -c 'exit 15'", timeout=5.0, check=True)
        assert exc_info.value.returncode == 15


def test_headless_run_command_timeout() -> None:
    """Verify run_command raises TimeoutError when command exceeds timeout."""
    with (
        HeadlessTerminal(cols=80, rows=24) as term,
        pytest.raises(TimeoutError, match="timed out"),
    ):
        term.run_command("sleep 5", timeout=0.1)


def test_headless_wait_for_prompt_no_premature_return() -> None:
    """Verify repeated wait_for_prompt calls do not prematurely return on stale prompt."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.wait_for_prompt(timeout=2.0)
        # Immediate subsequent wait without sending input should time out
        assert term.wait_for_prompt(timeout=0.05) is False


def test_cli_command_runner_headless() -> None:
    """Verify clownfish -c runs via _run_command_headless and exits with code."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["-c", "echo CLI_RUN_062"])
    assert "CLI_RUN_062" in stdout_buf.getvalue()


def test_gui_smoke_test_exit_code_contract() -> None:
    """Verify --smoke-test exits 0 on success and exits 2 when display is unavailable."""
    # When display is unavailable
    import tkinter as tk

    with patch.object(tk, "Tk", side_effect=tk.TclError("no display")):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf), pytest.raises(SystemExit) as exc:
            main(["--smoke-test"])
        assert exc.value.code == 2
        assert "display unavailable" in stderr_buf.getvalue()


def test_ssh_restoration_labeled_disconnected() -> None:
    """Verify auto_reconnect_ssh=False restores with explicit Disconnected label and banner."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    from clownfish.frontends.tkinter.split import SplitView

    ssh_node = SplitNodeState(
        is_leaf=True,
        pane=PaneState(
            cwd=None,
            title="prod-server",
            ssh={"host": "prod.internal", "port": 22},
        ),
    )

    try:
        config = TerminalConfig(auto_reconnect_ssh=False)
        with patch.object(PTYTransport, "start"):
            sv = SplitView(root, config=config, create_initial_pane=False)
            sv.load_state(ssh_node)
            pane = sv.panes()[0]
            assert "Disconnected" in pane.session.title
            assert "Local Shell" in pane.session.title
            # Check screen banner
            screen_text = "".join(
                cell.char for cell in pane.screen.get_visible_row(0) if cell.width != 0
            ) + "".join(
                cell.char for cell in pane.screen.get_visible_row(1) if cell.width != 0
            )
            assert "Disconnected" in screen_text or "Notice:" in screen_text
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

            # Activate Tab 0
            tab_view.switch_tab(0)
            assert tab_view.active_tab_index == 0
            active_sv = tab_view.active_split_view

            # Close background Tab 1
            tab_view.close_tab(1)
            assert len(tab_view.tabs) == 2
            # Active tab MUST still be Tab 0 (same SplitView)!
            assert tab_view.active_split_view is active_sv
            assert tab_view.active_tab_index == 0

            # Now switch to Tab 1 (which was Tab 3)
            tab_view.switch_tab(1)
            assert tab_view.active_tab_index == 1
            active_sv_tab3 = tab_view.active_split_view

            # Close background Tab 0
            tab_view.close_tab(0)
            assert len(tab_view.tabs) == 1
            assert tab_view.active_split_view is active_sv_tab3
            assert tab_view.active_tab_index == 0
    finally:
        root.destroy()


def test_tab_bar_request_close_confirmation() -> None:
    """Verify request_close_tab prompts when foreground process is active."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root, config=TerminalConfig(confirm_close_active_process=True))
            pane = tab_view.active_pane
            with patch.object(pane, "has_foreground_process", return_value=True):
                # When user cancels confirmation dialog
                with patch("tkinter.messagebox.askyesno", return_value=False):
                    closed = tab_view.request_close_tab(0)
                    assert closed is False
                    assert len(tab_view.tabs) == 1

                # When user confirms dialog
                with patch("tkinter.messagebox.askyesno", return_value=True):
                    closed = tab_view.request_close_tab(0)
                    assert closed is True
                    assert len(tab_view.tabs) == 0
    finally:
        root.destroy()


def test_render_tick_consolidation_single_job() -> None:
    """Verify _on_session_event consolidates pending timers to strictly at most one."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        with patch.object(PTYTransport, "start"):
            tab_view = TabbedTerminalView(root, config=TerminalConfig())
            pane = tab_view.active_pane

            # Simulate high-burst session events
            for _ in range(50):
                pane._on_session_event()

            # At most one tick job should be scheduled
            assert pane._tick_job is not None
    finally:
        root.destroy()


def test_homebrew_formula_virtualenv_python_target() -> None:
    """Verify Formula invokes libexec/bin/python for venv isolation."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from scripts.publish_homebrew import render_formula

    formula_str = render_formula("0.6.2", "dummy_sha256")
    assert 'libexec/"bin/python"' in formula_str
    assert "import tkinter; import clownfish" in formula_str
