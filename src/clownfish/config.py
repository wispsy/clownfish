"""Configuration options for clownfish terminal emulator."""

from __future__ import annotations

import dataclasses
import sys

from clownfish.core.models import DEFAULT_BG, DEFAULT_FG


@dataclasses.dataclass
class TerminalConfig:
    """Configurable terminal options."""

    cols: int = 80
    rows: int = 24
    max_scrollback: int = 10_000
    font_family: str = "Menlo" if sys.platform == "darwin" else "Monospace"
    font_size: int = 13
    default_fg: tuple[int, int, int] = DEFAULT_FG
    default_bg: tuple[int, int, int] = DEFAULT_BG
    cursor_color: str = "#e5e5e5"
    selection_color: str = "#4a90e2"
