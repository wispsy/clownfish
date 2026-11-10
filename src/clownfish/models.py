"""Data models and constants for clownfish terminal emulator."""

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
    # Zero-width control and format characters / combining characters
    if cp in (0x200B, 0x200C, 0x200D, 0xFE0E, 0xFE0F) or unicodedata.combining(char[0]):
        return 0
    # East Asian Width 'W' (Wide) and 'F' (Fullwidth) occupy 2 columns
    eaw = unicodedata.east_asian_width(char[0])
    if eaw in ("W", "F"):
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

    def copy(self) -> "Style":
        return Style(
            self.fg, self.bg, self.bold, self.italic, self.underline, self.reverse
        )


@dataclasses.dataclass(slots=True)
class Cell:
    """Individual character cell on the terminal grid."""

    char: str = " "
    style: Style = dataclasses.field(default_factory=Style)
    url: str | None = None  # OSC 8 Hyperlink target
    width: int = 1  # 1 for regular, 2 for wide lead cell, 0 for wide continuation spacer


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
