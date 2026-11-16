"""Tests for TerminalPane, SplitView, and TabbedTerminalView."""

from __future__ import annotations

import pytest

import clownfish


def test_public_tab_and_pane_exports() -> None:
    assert hasattr(clownfish, "TerminalPane")
    assert hasattr(clownfish, "SplitView")
    assert hasattr(clownfish, "TabbedTerminalView")
    assert hasattr(clownfish, "SearchMatch")
    assert hasattr(clownfish, "SearchState")
    assert hasattr(clownfish, "search_screen")


def test_is_application_shortcut() -> None:
    from unittest.mock import MagicMock

    from clownfish.frontends.tkinter.input import is_application_shortcut

    # Helper mock
    def make_event(keysym: str, state: int) -> MagicMock:
        ev = MagicMock()
        ev.keysym = keysym
        ev.state = state
        return ev

    # Plain keys should not be application shortcuts
    assert not is_application_shortcut(make_event("a", 0))
    assert not is_application_shortcut(make_event("Return", 0))
    assert not is_application_shortcut(make_event("c", 0x4))  # Ctrl+C in terminal (SIGINT)

    # Ctrl+Tab should be application shortcut
    assert is_application_shortcut(make_event("Tab", 0x4))

    # Ctrl+Shift+T, Ctrl+Shift+W
    assert is_application_shortcut(make_event("t", 0x4 | 0x1))
    assert is_application_shortcut(make_event("w", 0x4 | 0x1))

    # Alt+1..9
    assert is_application_shortcut(make_event("1", 0x8))


def test_tabbed_view_and_split_lifecycle() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError):
        pytest.skip("Tkinter or X11/macOS display not available in this test environment")

    try:
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        tab_view = TabbedTerminalView(root)

        # Initially 1 tab
        assert len(tab_view.tabs) == 1
        assert tab_view.active_tab_index == 0
        assert tab_view.active_pane is not None

        # Add second tab
        tab_view.new_tab("Shell 2")
        assert len(tab_view.tabs) == 2
        assert tab_view.active_tab_index == 1
        assert tab_view.tabs[1][0] == "Shell 2"

        # Switch back to tab 0
        tab_view.switch_tab(0)
        assert tab_view.active_tab_index == 0

        # Cycle tabs
        tab_view.next_tab()
        assert tab_view.active_tab_index == 1
        tab_view.prev_tab()
        assert tab_view.active_tab_index == 0

        # Split pane in active tab
        sv1 = tab_view.active_split_view
        assert sv1 is not None
        assert len(sv1.panes()) == 1

        pane2 = sv1.split_horizontal()
        assert len(sv1.panes()) == 2
        assert sv1.active_pane == pane2

        # In-buffer search on pane2
        pane2.open_search()
        assert pane2._search_frame is not None
        pane2.close_search()

        # Close split pane
        sv1.close_pane(pane2)
        assert len(sv1.panes()) == 1

        # Close second tab
        tab_view.close_tab(1)
        assert len(tab_view.tabs) == 1
        assert tab_view.active_tab_index == 0

    finally:
        try:
            for _, sv in tab_view.tabs:
                for p in sv.panes():
                    p.close()
            root.destroy()
        except (tk.TclError, OSError):
            pass


def test_nested_split_tree_and_selection() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError):
        pytest.skip("Tkinter or X11/macOS display not available in this test environment")

    try:
        from clownfish.core.models import Selection
        from clownfish.frontends.tkinter.split import SplitView

        sv = SplitView(root)
        initial_pane = sv.active_pane
        assert initial_pane is not None
        assert len(sv.panes()) == 1

        # Test selection property synchronization
        assert not initial_pane.selection.active
        initial_pane.input_handler.selection = Selection(
            start_col=2, start_row=1, end_col=10, end_row=1, active=True
        )
        assert initial_pane.selection.active
        assert initial_pane.selection.start_col == 2

        # 1. Split vertically: creates side-by-side panes
        pane_right = sv.split_vertical()
        assert len(sv.panes()) == 2
        assert sv.active_pane == pane_right

        # 2. Split horizontally inside the right pane: creates nested vertical split in right pane
        pane_bottom_right = sv.split_horizontal()
        assert len(sv.panes()) == 3
        assert sv.active_pane == pane_bottom_right

        # 3. Close the nested pane: collapses cleanly without TclError
        sv.close_pane(pane_bottom_right)
        assert len(sv.panes()) == 2
        assert pane_bottom_right not in sv.panes()

        # 4. Close the other split pane: collapses back to initial pane
        sv.close_pane(pane_right)
        assert len(sv.panes()) == 1
        assert sv.active_pane == initial_pane

    finally:
        try:
            for p in sv.panes():
                p.close()
            root.destroy()
        except (tk.TclError, OSError):
            pass

