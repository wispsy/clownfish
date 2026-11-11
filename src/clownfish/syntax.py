"""Syntax highlighting integration using escape-colors (escape_colors.syntax)."""

from collections.abc import Iterable
from typing import Any

import escape_colors.syntax as ec_syntax

from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer


def highlight_code(
    source_or_tokens: str | Iterable[Any],
    language: str | None = None,
    theme: str = "default",
) -> str:
    """Highlight source code into ANSI escape sequence formatted text using escape-colors."""
    return ec_syntax.highlight(source_or_tokens, language=language, theme=theme)


def print_highlighted(
    screen: ScreenBuffer,
    source: str,
    language: str = "python",
    theme: str = "default",
) -> None:
    """Render syntax-highlighted code directly into a Clownfish ScreenBuffer."""
    ansi_text = highlight_code(source, language=language, theme=theme)
    parser = VT100Parser(screen)
    parser.feed(ansi_text)
