"""Data models and constants for clownfish terminal emulator."""

import dataclasses

DEFAULT_FG: tuple[int, int, int] = (229, 229, 229)
DEFAULT_BG: tuple[int, int, int] = (20, 20, 25)
WORD_DELIMITERS: set[str] = set(" \t\n\r()[]{}\"'`:;,=")


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
