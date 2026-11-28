"""Built-in color themes and theme registry for Clownfish."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clownfish.config import TerminalConfig


@dataclasses.dataclass(frozen=True, slots=True)
class Theme:
    """Color theme specification for terminal text, backgrounds, and chrome."""

    name: str
    display_name: str
    default_fg: tuple[int, int, int]
    default_bg: tuple[int, int, int]
    cursor_color: str
    selection_color: str
    search_bg: str = "#d7ba7d"
    search_fg: str = "#141419"
    tab_bar_bg: str = "#18181c"
    tab_active_bg: str = "#282830"
    tab_fg: str = "#a0a0a8"
    tab_active_fg: str = "#ffffff"


THEMES: dict[str, Theme] = {
    "clownfish_dark": Theme(
        name="clownfish_dark",
        display_name="Clownfish Dark",
        default_fg=(229, 229, 229),
        default_bg=(20, 20, 25),
        cursor_color="#e5e5e5",
        selection_color="#4a90e2",
        search_bg="#d7ba7d",
        search_fg="#141419",
        tab_bar_bg="#18181c",
        tab_active_bg="#282830",
        tab_fg="#a0a0a8",
        tab_active_fg="#ffffff",
    ),
    "nord": Theme(
        name="nord",
        display_name="Nord",
        default_fg=(216, 222, 233),
        default_bg=(46, 52, 64),
        cursor_color="#eceff4",
        selection_color="#434c5e",
        search_bg="#ebcb8b",
        search_fg="#2e3440",
        tab_bar_bg="#242933",
        tab_active_bg="#3b4252",
        tab_fg="#d8dee9",
        tab_active_fg="#88c0d0",
    ),
    "dracula": Theme(
        name="dracula",
        display_name="Dracula",
        default_fg=(248, 248, 242),
        default_bg=(40, 42, 54),
        cursor_color="#f8f8f2",
        selection_color="#44475a",
        search_bg="#f1fa8c",
        search_fg="#282a36",
        tab_bar_bg="#191a21",
        tab_active_bg="#44475a",
        tab_fg="#6272a4",
        tab_active_fg="#bd93f9",
    ),
    "solarized_dark": Theme(
        name="solarized_dark",
        display_name="Solarized Dark",
        default_fg=(131, 148, 150),
        default_bg=(0, 43, 54),
        cursor_color="#93a1a1",
        selection_color="#073642",
        search_bg="#b58900",
        search_fg="#002b36",
        tab_bar_bg="#001e26",
        tab_active_bg="#073642",
        tab_fg="#586e75",
        tab_active_fg="#268bd2",
    ),
    "solarized_light": Theme(
        name="solarized_light",
        display_name="Solarized Light",
        default_fg=(101, 123, 131),
        default_bg=(253, 246, 227),
        cursor_color="#586e75",
        selection_color="#eee8d5",
        search_bg="#b58900",
        search_fg="#fdf6e3",
        tab_bar_bg="#f5eed9",
        tab_active_bg="#eee8d5",
        tab_fg="#93a1a1",
        tab_active_fg="#268bd2",
    ),
    "catppuccin_mocha": Theme(
        name="catppuccin_mocha",
        display_name="Catppuccin Mocha",
        default_fg=(205, 214, 244),
        default_bg=(30, 30, 46),
        cursor_color="#f5e0dc",
        selection_color="#45475a",
        search_bg="#f9e2af",
        search_fg="#1e1e2e",
        tab_bar_bg="#11111b",
        tab_active_bg="#313244",
        tab_fg="#a6adc8",
        tab_active_fg="#cba6f7",
    ),
    "monokai": Theme(
        name="monokai",
        display_name="Monokai",
        default_fg=(248, 248, 242),
        default_bg=(39, 40, 34),
        cursor_color="#f8f8f0",
        selection_color="#49483e",
        search_bg="#e6db74",
        search_fg="#272822",
        tab_bar_bg="#1e1f1c",
        tab_active_bg="#3e3d32",
        tab_fg="#75715e",
        tab_active_fg="#a6e22e",
    ),
    "one_dark": Theme(
        name="one_dark",
        display_name="One Dark",
        default_fg=(171, 178, 191),
        default_bg=(40, 44, 52),
        cursor_color="#528bff",
        selection_color="#3e4451",
        search_bg="#e5c07b",
        search_fg="#282c34",
        tab_bar_bg="#21252b",
        tab_active_bg="#2c313a",
        tab_fg="#5c6370",
        tab_active_fg="#61afef",
    ),
}


def get_theme(name: str) -> Theme:
    """Return theme by key, falling back to clownfish_dark."""
    return THEMES.get(name, THEMES["clownfish_dark"])


def list_themes() -> list[tuple[str, str]]:
    """Return list of (key, display_name) for all registered themes."""
    return [(k, t.display_name) for k, t in THEMES.items()]


def apply_theme_to_config(config: TerminalConfig, theme_name: str) -> bool:
    """Apply theme palette values to a TerminalConfig object in-place."""
    if theme_name not in THEMES:
        return False
    t = THEMES[theme_name]
    config.theme = theme_name
    config.default_fg = t.default_fg
    config.default_bg = t.default_bg
    config.cursor_color = t.cursor_color
    config.selection_color = t.selection_color
    config.search_bg = t.search_bg
    config.search_fg = t.search_fg
    config.tab_bar_bg = t.tab_bar_bg
    config.tab_active_bg = t.tab_active_bg
    config.tab_fg = t.tab_fg
    config.tab_active_fg = t.tab_active_fg
    return True
