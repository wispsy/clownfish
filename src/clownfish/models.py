"""Data models and constants for clownfish terminal emulator (legacy import path)."""

from clownfish.core.keyboard import encode_kitty_key
from clownfish.core.models import (
    DEFAULT_BG,
    DEFAULT_FG,
    WORD_DELIMITERS,
    Cell,
    PromptMarker,
    Selection,
    Style,
    char_width,
)

__all__ = [
    "DEFAULT_BG",
    "DEFAULT_FG",
    "WORD_DELIMITERS",
    "Cell",
    "PromptMarker",
    "Selection",
    "Style",
    "char_width",
    "encode_kitty_key",
]
