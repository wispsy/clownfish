"""Data models and constants for clownfish terminal emulator."""

from __future__ import annotations

import dataclasses
import unicodedata

DEFAULT_FG: tuple[int, int, int] = (229, 229, 229)
DEFAULT_BG: tuple[int, int, int] = (20, 20, 25)
WORD_DELIMITERS: set[str] = set(" \t\n\r()[]{}\"'`:;,=")


def char_width(char: str) -> int:
    """Return the display column width (0, 1, or 2) of a character in monospace terminals."""
    if not char:
        return 0
    cp = ord(char[0])
    # Zero-width control, format, combining marks, Fitzpatrick skin tone modifiers, and variation selectors
    if (
        cp in (0x200B, 0x200C, 0x200D, 0xFE0E, 0xFE0F, 0x20E3)
        or (0x1F3FB <= cp <= 0x1F3FF)  # Fitzpatrick emoji modifiers (skin tone)
        or (0xE0020 <= cp <= 0xE007F)  # Tags
        or unicodedata.combining(char[0])
    ):
        return 0
    # East Asian Width 'W' (Wide) and 'F' (Fullwidth) occupy 2 columns
    eaw = unicodedata.east_asian_width(char[0])
    if eaw in ("W", "F"):
        return 2
    # Standard emoji and pictograph ranges occupying 2 columns in modern terminals
    if (
        (0x1F300 <= cp <= 0x1F5FF)
        or (0x1F600 <= cp <= 0x1F64F)
        or (0x1F680 <= cp <= 0x1F6FF)
        or (0x1F900 <= cp <= 0x1F9FF)
        or (0x1FA70 <= cp <= 0x1FAFF)
        or (0x2600 <= cp <= 0x26FF)
        or (0x2700 <= cp <= 0x27BF)
    ):
        return 2
    return 1


@dataclasses.dataclass(slots=True)
class Style:
    """Styling attributes for a terminal cell."""

    fg: tuple[int, int, int] = DEFAULT_FG
    bg: tuple[int, int, int] = DEFAULT_BG
    bold: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False

    def copy(self) -> Style:
        return Style(
            self.fg, self.bg, self.bold, self.italic, self.underline, self.reverse
        )

    def is_default(self) -> bool:
        """Return True if style has default foreground, background, and no attributes."""
        return (
            self.fg == DEFAULT_FG
            and self.bg == DEFAULT_BG
            and not self.bold
            and not self.italic
            and not self.underline
            and not self.reverse
        )


@dataclasses.dataclass(slots=True)
class Cell:
    """Individual character cell on the terminal grid."""

    char: str = " "
    style: Style = dataclasses.field(default_factory=Style)
    url: str | None = None  # OSC 8 Hyperlink target
    width: int = 1  # 1 for regular, 2 for wide lead cell, 0 for wide continuation spacer


class Row(list[Cell]):
    """Physical row of cells with soft-wrap continuation metadata."""

    def __init__(self, cells: list[Cell] | None = None, is_wrapped: bool = False) -> None:
        super().__init__(cells if cells is not None else [])
        self.is_wrapped = is_wrapped

    def copy(self) -> Row:
        return Row([dataclasses.replace(c, style=c.style.copy()) for c in self], is_wrapped=self.is_wrapped)


@dataclasses.dataclass
class PromptMarker:
    """Semantic prompt boundary captured via OSC 133 with absolute row tracking."""

    row: int
    command: str = ""
    exit_code: int | None = None


@dataclasses.dataclass
class Selection:
    """Tracks mouse selection coordinates in terminal character space."""

    active: bool = False
    start_col: int = 0
    start_row: int = 0
    end_col: int = 0
    end_row: int = 0

    def is_empty(self) -> bool:
        return not self.active or (
            self.start_col == self.end_col and self.start_row == self.end_row
        )

    def normalized(self) -> tuple[tuple[int, int], tuple[int, int]]:
        p1 = (self.start_col, self.start_row)
        p2 = (self.end_col, self.end_row)
        if (p1[1], p1[0]) <= (p2[1], p2[0]):
            return p1, p2
        return p2, p1
