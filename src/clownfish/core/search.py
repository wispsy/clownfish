"""In-buffer text search for active grid and scrollback history."""

from __future__ import annotations

import dataclasses
import re

from clownfish.core.screen import ScreenBuffer


@dataclasses.dataclass(slots=True)
class SearchMatch:
    """Represents a text match inside the terminal screen buffer."""

    absolute_row: int
    start_col: int
    end_col: int  # exclusive
    text: str
    is_scrollback: bool
    view_row: int  # relative row index within scrollback or grid


def search_screen(
    screen: ScreenBuffer,
    query: str,
    case_sensitive: bool = False,
    regex: bool = False,
) -> list[SearchMatch]:
    """Find all occurrences of query across scrollback and visible grid."""
    if not query:
        return []

    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        try:
            pattern = re.compile(query, flags)
        except re.error:
            return []
    else:
        pattern = re.compile(re.escape(query), flags)

    matches: list[SearchMatch] = []
    scrollback_len = len(screen.scrollback)

    # 1. Search scrollback rows
    for sb_idx, row in enumerate(screen.scrollback):
        line_text = "".join(cell.char for cell in row if cell.width != 0)
        for m in pattern.finditer(line_text):
            matches.append(
                SearchMatch(
                    absolute_row=sb_idx,
                    start_col=m.start(),
                    end_col=m.end(),
                    text=m.group(0),
                    is_scrollback=True,
                    view_row=sb_idx,
                )
            )

    # 2. Search active grid rows
    for grid_idx in range(screen.rows):
        row = screen.grid[grid_idx]
        line_text = "".join(cell.char for cell in row if cell.width != 0)
        for m in pattern.finditer(line_text):
            matches.append(
                SearchMatch(
                    absolute_row=scrollback_len + grid_idx,
                    start_col=m.start(),
                    end_col=m.end(),
                    text=m.group(0),
                    is_scrollback=False,
                    view_row=grid_idx,
                )
            )

    return matches


class SearchState:
    """Manages navigation state and active index across search matches."""

    def __init__(self) -> None:
        self.query: str = ""
        self.matches: list[SearchMatch] = []
        self.current_index: int = -1

    def set_results(self, query: str, matches: list[SearchMatch]) -> None:
        """Update results with a new query and list of matches."""
        self.query = query
        self.matches = matches
        if self.matches:
            self.current_index = 0
        else:
            self.current_index = -1

    def clear(self) -> None:
        """Reset search state."""
        self.query = ""
        self.matches = []
        self.current_index = -1

    @property
    def current_match(self) -> SearchMatch | None:
        """Return currently selected match or None."""
        if 0 <= self.current_index < len(self.matches):
            return self.matches[self.current_index]
        return None

    def next_match(self) -> SearchMatch | None:
        """Cycle forward to the next match."""
        if not self.matches:
            return None
        self.current_index = (self.current_index + 1) % len(self.matches)
        return self.matches[self.current_index]

    def prev_match(self) -> SearchMatch | None:
        """Cycle backward to the previous match."""
        if not self.matches:
            return None
        self.current_index = (self.current_index - 1) % len(self.matches)
        return self.matches[self.current_index]

    @property
    def total(self) -> int:
        return len(self.matches)
