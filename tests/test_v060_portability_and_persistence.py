"""Tests for Milestone 0.6.0 portability, remote SSH sessions, and layout persistence."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import clownfish
from clownfish import HeadlessTerminal, main
from clownfish.config import TerminalConfig
from clownfish.session.persistence import (
    PaneState,
    SessionState,
    SplitNodeState,
    TabState,
)
from clownfish.transports.ssh import SSHTransport


def test_version_bump_060() -> None:
    """Verify package version is at least 0.6.0."""
    assert clownfish.__version__ >= "0.6.0"


def test_headless_terminal_live_execution() -> None:
    """Test HeadlessTerminal running a real shell command and capturing output."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        assert term.is_alive()
        term.send_input("echo CLOWNFISH_HEADLESS_OK\n")
        matched = term.wait_for_text("CLOWNFISH_HEADLESS_OK", timeout=3.0)
        assert matched is True, "Expected command output to appear on screen"

        text = term.get_text()
        assert "CLOWNFISH_HEADLESS_OK" in text

        # Check cursor position
        col, row = term.cursor_position
        assert 0 <= col < 80
        assert 0 <= row < 24


def test_headless_terminal_line_indexing() -> None:
    """Verify single line retrieval and bounds checking."""
    with HeadlessTerminal(cols=40, rows=10) as term:
        line_0 = term.get_line(0)
        assert isinstance(line_0, str)

        with pytest.raises(IndexError):
            term.get_line(100)


def test_session_state_serialization() -> None:
    """Test serializing and deserializing complex session states."""
    leaf_local = SplitNodeState(
        is_leaf=True,
        pane=PaneState(cwd="/tmp", title="local-shell"),
    )
    leaf_ssh = SplitNodeState(
        is_leaf=True,
        pane=PaneState(
            cwd=None,
            title="remote-prod",
            ssh={"host": "prod.example.com", "port": 2222, "user": "admin", "identity_file": "~/.ssh/id_rsa"},
        ),
    )
    nested_split = SplitNodeState(
        is_leaf=False,
        orientation="horizontal",
        children=[leaf_local, leaf_ssh],
    )

    tab_1 = TabState(title="Dev", root=nested_split)
    tab_2 = TabState(title="Logs", root=SplitNodeState(is_leaf=True, pane=PaneState(cwd="/var/log")))

    state = SessionState(version=1, active_tab_index=1, tabs=[tab_1, tab_2])
    data = state.to_dict()

    restored = SessionState.from_dict(data)
    assert restored.version == 1
    assert restored.active_tab_index == 1
    assert len(restored.tabs) == 2
    assert restored.tabs[0].title == "Dev"
    assert restored.tabs[0].root.is_leaf is False
    assert restored.tabs[0].root.orientation == "horizontal"
    assert len(restored.tabs[0].root.children) == 2
    assert restored.tabs[0].root.children[1].pane.ssh["host"] == "prod.example.com"
    assert restored.tabs[1].title == "Logs"
    assert restored.tabs[1].root.pane.cwd == "/var/log"


def test_session_state_file_persistence() -> None:
    """Test saving and loading SessionState to and from disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "session_state.json"

        # Missing file returns None
        assert SessionState.load(state_file) is None

        # Write and read back
        tab = TabState(title="Main", root=SplitNodeState(is_leaf=True, pane=PaneState(cwd="/etc")))
        state = SessionState(version=1, active_tab_index=0, tabs=[tab])
        saved_path = state.save(state_file)
        assert saved_path == state_file
        assert state_file.exists()

        loaded = SessionState.load(state_file)
        assert loaded is not None
        assert len(loaded.tabs) == 1
        assert loaded.tabs[0].root.pane.cwd == "/etc"

        # Corrupted JSON returns None gracefully
        state_file.write_text("invalid json content!@#$", encoding="utf-8")
        assert SessionState.load(state_file) is None


def test_ssh_transport_command_construction() -> None:
    """Verify OpenSSH argument formatting with custom parameters."""
    transport = SSHTransport(
        host="example.com",
        port=2202,
        user="deploy",
        identity_file="/custom/id_ed25519",
        extra_args=["-o", "StrictHostKeyChecking=no"],
    )
    cmd = transport._build_ssh_command()
    assert cmd[0] == "ssh"
    assert "-tt" in cmd
    assert "-p" in cmd
    assert "2202" in cmd
    assert "-l" in cmd
    assert "deploy" in cmd
    assert "-i" in cmd
    assert "/custom/id_ed25519" in cmd
    assert "StrictHostKeyChecking=no" in cmd
    assert cmd[-1] == "example.com"


def test_cli_ssh_argument_parsing() -> None:
    """Verify clownfish ssh CLI command parsing."""
    with (
        patch("clownfish.transports.ssh.SSHTransport.__init__", return_value=None) as mock_ssh_init,
        patch("tkinter.Tk"),
        patch("clownfish.frontends.tkinter.app.TkTerminalApp"),
    ):
        main(["ssh", "deploy@remote.org", "-p", "2222", "-i", "~/.ssh/id_rsa"])
        mock_ssh_init.assert_called_once()
        call_kwargs = mock_ssh_init.call_args[1]
        assert call_kwargs["host"] == "remote.org"
        assert call_kwargs["user"] == "deploy"
        assert call_kwargs["port"] == 2222
        assert call_kwargs["identity_file"] == "~/.ssh/id_rsa"


def test_cli_restore_flags() -> None:
    """Verify --no-restore and --restore CLI flags."""
    with patch("clownfish.config.TerminalConfig.load") as mock_load:
        config_obj = TerminalConfig(restore_session=True)
        mock_load.return_value = config_obj

        with patch("tkinter.Tk"), patch("clownfish.frontends.tkinter.app.TkTerminalApp"):
            main(["--no-restore"])
            assert config_obj.restore_session is False


def test_cli_help_shows_v060_options() -> None:
    """Verify --help documents ssh and session restoration options."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["--help"])
    output = stdout_buf.getvalue()
    assert "ssh <destination>" in output
    assert "--restore" in output
    assert "--no-restore" in output
    assert "--headless" in output


def test_gui_tab_and_split_state_persistence() -> None:
    """Verify dump_state and load_state on TabbedTerminalView and SplitView."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError):
        pytest.skip("Tkinter or display not available")

    try:
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        tab_view = TabbedTerminalView(root)
        # Create a second tab and split it
        sv_tab2 = tab_view.new_tab(title="Second Tab")
        sv_tab2.split_horizontal()

        # Dump state
        dumped_state = tab_view.dump_state()
        assert len(dumped_state.tabs) == 2
        assert dumped_state.tabs[1].title == "Second Tab"
        assert dumped_state.tabs[1].root.is_leaf is False
        assert len(dumped_state.tabs[1].root.children) == 2

        # Create a new TabbedTerminalView and load the state
        new_tab_view = TabbedTerminalView(root)
        success = new_tab_view.load_state(dumped_state)
        assert success is True
        assert len(new_tab_view.tabs) == 2
        assert new_tab_view.tabs[1][0] == "Second Tab"
        assert len(new_tab_view.tabs[1][1].panes()) == 2
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def test_new_ssh_tab_creation() -> None:
    """Verify creating an SSH tab on TabbedTerminalView."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError):
        pytest.skip("Tkinter or display not available")

    try:
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        with patch("clownfish.transports.ssh.SSHTransport.start", return_value=None):
            tab_view = TabbedTerminalView(root)
            ssh_sv = tab_view.new_ssh_tab(
                host="server.internal",
                user="admin",
                port=2222,
            )
            assert len(tab_view.tabs) == 2
            assert "server.internal" in tab_view.tabs[-1][0]
            assert "🌐" in tab_view.tabs[-1][0]
            assert len(ssh_sv.panes()) == 1
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass

