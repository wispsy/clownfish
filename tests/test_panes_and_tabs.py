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
