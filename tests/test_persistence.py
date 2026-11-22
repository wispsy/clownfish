"""Behavioral tests for layout and session state persistence."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from clownfish import main
from clownfish.config import TerminalConfig
from clownfish.session.persistence import (
    PaneState,
    SessionState,
    SplitNodeState,
    TabState,
)


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


def test_cli_restore_flags() -> None:
    """Verify --no-restore and --restore CLI flags."""
    with patch("clownfish.config.TerminalConfig.load") as mock_load:
        config_obj = TerminalConfig(restore_session=True)
        mock_load.return_value = config_obj

        with patch("tkinter.Tk"), patch("clownfish.frontends.tkinter.app.TkTerminalApp"):
            main(["--no-restore"])
            assert config_obj.restore_session is False


def test_gui_tab_and_split_state_persistence() -> None:
    """Verify dump_state and load_state on TabbedTerminalView and SplitView."""
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
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
        except (tk.TclError, RuntimeError):
            pass
