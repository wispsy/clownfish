"""Core terminal models, keyboard encoding, parser, and screen buffer."""

from clownfish.core.keyboard import encode_key_press, encode_kitty_key
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
from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.core.search import SearchMatch, SearchState, search_screen

__all__ = [
    "DEFAULT_BG",
    "DEFAULT_FG",
    "WORD_DELIMITERS",
    "Cell",
    "PromptMarker",
    "ScreenBuffer",
    "SearchMatch",
    "SearchState",
    "Selection",
    "Style",
    "VT100Parser",
    "char_width",
    "encode_key_press",
    "encode_kitty_key",
    "search_screen",
]
