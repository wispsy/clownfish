"""Tests for UI/UX features: scrollbar navigation, padding, menus, and settings dialog."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.settings import SettingsDialog
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport


class DummyTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self._alive = True

    def start(self) -> None:
        pass

    def write(self, data: bytes) -> None:
        pass

    def resize(self, cols: int, rows: int) -> None:
        pass

    def close(self) -> None:
        self._alive = False

    def is_alive(self) -> bool:
        return self._alive


def test_renderer_padding_configuration() -> None:
    cfg = TerminalConfig(padding_x=12, padding_y=8)
    assert cfg.padding_x == 12
    assert cfg.padding_y == 8


def test_terminal_pane_scrollbar_actions() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except ImportError, tk.TclError, RuntimeError:
        pytest.skip("Tkinter display not available")

    try:
        transport = DummyTransport()
        session = TerminalSession(cols=40, rows=10, max_scrollback=100, transport=transport)

        # Add 30 lines to scrollback
        for i in range(30):
            session.feed_text(f"Line {i}\r\n")

        pane = TerminalPane(root, session=session, config=TerminalConfig())

        # Test scrollbar moveto
        pane._on_scrollbar_action("moveto", "0.0")
        assert pane.screen.scroll_offset == len(pane.screen.scrollback)

        pane._on_scrollbar_action("moveto", "1.0")
        assert pane.screen.scroll_offset == 0

        # Test scroll units
        pane._on_scrollbar_action("moveto", "0.5")
        current_offset = pane.screen.scroll_offset
        pane._on_scrollbar_action("scroll", "-1", "units")
        assert pane.screen.scroll_offset >= current_offset

        # Test scroll pages
        pane._on_scrollbar_action("scroll", "1", "pages")
        assert pane.screen.scroll_offset <= current_offset

        # Test apply_config updating scrollbar visibility and padding
        new_cfg = TerminalConfig(padding_x=10, padding_y=10, show_scrollbar=False)
        pane.apply_config(new_cfg)
        assert pane.renderer.pad_x == 10
        assert pane.renderer.pad_y == 10
        assert not pane.scrollbar.winfo_viewable()

        pane.close()
    finally:
        root.destroy()


def test_settings_dialog_initialization() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except ImportError, tk.TclError, RuntimeError:
        pytest.skip("Tkinter display not available")

    try:
        cfg = TerminalConfig()
        applied_configs: list[TerminalConfig] = []

        dialog = SettingsDialog(root, cfg, on_apply=lambda c: applied_configs.append(c))

        # Test applying settings through dialog
        dialog.font_size_var.set(16)
        dialog.theme_var.set("nord")
        dialog.pad_x_var.set(12)
        dialog.pad_y_var.set(10)
        dialog.show_scrollbar_var.set(True)
        dialog.screen_reader_var.set(True)

        dialog._on_save()
        assert len(applied_configs) == 1
        updated = applied_configs[0]
        assert updated.font_size == 16
        assert updated.theme == "nord"
        assert updated.padding_x == 12
        assert updated.padding_y == 10
        assert updated.show_scrollbar is True
        assert updated.screen_reader_mode is True

        dialog.destroy()
    finally:
        root.destroy()


def test_app_menu_and_actions() -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
    except ImportError, tk.TclError, RuntimeError:
        pytest.skip("Tkinter display not available")

    try:
        from clownfish.frontends.tkinter.app import TkTerminalApp

        with patch("clownfish.transports.pty.PTYTransport.start"):
            app = TkTerminalApp(root, config=TerminalConfig())
            assert app.root.cget("menu") != ""

            # Test zoom in / out / reset
            orig_size = app.config.font_size
            app._zoom(2)
            assert app.config.font_size == orig_size + 2
            app._reset_zoom()
            assert app.config.font_size == 13

            # Test scrollbar toggle
            initial_sb = app.config.show_scrollbar
            app._toggle_scrollbar()
            assert app.config.show_scrollbar is not initial_sb

            # Test screen reader toggle
            initial_a11y = app.config.screen_reader_mode
            app._toggle_screen_reader()
            assert app.config.screen_reader_mode is not initial_a11y

            # Test select all
            app._select_all()
            sel = app.active_pane.selection
            assert sel.active is True
            assert sel.start == (0, 0)
            assert sel.end == (app.active_pane.cols - 1, app.active_pane.rows - 1)

            # Clean up
            for _, sv in app.tab_view.tabs:
                for pane in sv.panes():
                    pane.close()
    finally:
        root.destroy()
