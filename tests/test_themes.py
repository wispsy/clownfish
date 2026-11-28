"""Tests for theme management and color palettes."""

from __future__ import annotations

from clownfish.config import TerminalConfig
from clownfish.themes import THEMES, apply_theme_to_config, get_theme, list_themes


def test_list_themes() -> None:
    theme_pairs = list_themes()
    theme_ids = [t[0] for t in theme_pairs]
    assert "clownfish_dark" in theme_ids
    assert "nord" in theme_ids
    assert "dracula" in theme_ids
    assert "solarized_dark" in theme_ids
    assert "solarized_light" in theme_ids
    assert "catppuccin_mocha" in theme_ids
    assert "monokai" in theme_ids
    assert "one_dark" in theme_ids
    assert len(theme_pairs) == 8


def test_get_theme_lookup() -> None:
    dracula = get_theme("dracula")
    assert dracula.name == "dracula"
    assert dracula.display_name == "Dracula"
    assert dracula.default_bg == (40, 42, 54)
    assert dracula.cursor_color == "#f8f8f2"


def test_get_theme_fallback() -> None:
    unknown = get_theme("nonexistent_theme")
    assert unknown.name == "clownfish_dark"


def test_apply_theme_to_config() -> None:
    cfg = TerminalConfig()
    apply_theme_to_config(cfg, "nord")

    assert cfg.theme == "nord"
    assert cfg.cursor_color == "#eceff4"
    assert cfg.selection_color == "#434c5e"
    assert cfg.tab_bar_bg == "#242933"


def test_theme_properties_complete() -> None:
    for theme_id, _ in list_themes():
        theme = THEMES[theme_id]
        assert theme.name == theme_id
        assert theme.display_name
        assert isinstance(theme.default_bg, tuple) and len(theme.default_bg) == 3
        assert isinstance(theme.default_fg, tuple) and len(theme.default_fg) == 3
        assert theme.cursor_color.startswith("#")
        assert theme.selection_color.startswith("#")
        assert theme.tab_bar_bg.startswith("#")
