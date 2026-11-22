"""Behavioral tests for SSH transports, remote tabs, and CLI SSH execution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from clownfish import main
from clownfish.config import TerminalConfig
from clownfish.session.persistence import (
    PaneState,
    SplitNodeState,
)
from clownfish.transports.pty import PTYTransport
from clownfish.transports.ssh import SSHTransport


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


def test_ssh_initial_tab_no_local_shell_leak() -> None:
    """Verify launching an SSH session does not spawn an orphaned local shell."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        with patch.object(PTYTransport, "start") as mock_pty_start, patch.object(SSHTransport, "start"):
            ssh_transport = SSHTransport(host="remote.test")
            from clownfish.session.session import TerminalSession

            ssh_session = TerminalSession(transport=ssh_transport, title="SSH: remote.test")
            tab_view = TabbedTerminalView(root, initial_session=ssh_session)

            assert len(tab_view.tabs) == 1
            panes = tab_view.active_split_view.panes()
            assert len(panes) == 1
            assert panes[0].session is ssh_session
            # PTYTransport start should not have been called for initial tab
            mock_pty_start.assert_not_called()
    finally:
        root.destroy()


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
            ) + "".join(cell.char for cell in pane.screen.get_visible_row(1) if cell.width != 0)
            assert "Disconnected" in screen_text or "Notice:" in screen_text
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
        config_no_reconnect = TerminalConfig(auto_reconnect_ssh=False)
        with patch.object(PTYTransport, "start"):
            sv = SplitView(root, config=config_no_reconnect, create_initial_pane=False)
            sv.load_state(ssh_node)
            assert len(sv.panes()) == 1
    finally:
        root.destroy()


def test_new_ssh_tab_creation() -> None:
    """Verify creating an SSH tab on TabbedTerminalView."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        pytest.skip("Tkinter display not available")

    try:
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        with patch("clownfish.transports.ssh.SSHTransport.start", return_value=None):
            tab_view = TabbedTerminalView(root)
            tab_view.new_ssh_tab(
                host="server.internal",
                user="admin",
                port=2222,
            )
            assert len(tab_view.tabs) == 2
    finally:
        root.destroy()
