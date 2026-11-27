"""Ligature detection, font shaping tokens, and monospace run segmentation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clownfish.core.models import Cell, Style

# Common programming ligatures recognized in modern developer fonts
# Ordered from longest to shortest to ensure greedy matching
LIGATURE_PATTERNS: tuple[str, ...] = (
    # 5-character
    "<--->",
    # 4-character
    "<---",
    "<!--",
    "<-->",
    "====",
    "===>",
    "!==",
    "=/==",
    # 3-character
    "===",
    "!==",
    "-->",
    "<--",
    "<=>",
    "=>>",
    "<<=",
    ">>=",
    ">>>",
    "<<<",
    "=<<",
    "###",
    ":::",
    "/==",
    "\\==",
    "...",
    # 2-character
    "!=",
    "==",
    "->",
    "<-",
    "=>",
    "<=",
    ">=",
    ":=",
    "/*",
    "*/",
    "//",
    "::",
    "..",
    "||",
    "&&",
    "++",
    "--",
    "~~",
    "??",
    "%%",
    ">>",
    "<<",
    "=~",
    "!~",
    "|>",
    "<|",
    "~>",
    "<~",
    "?:",
    "!!",
)

# Precompile regex matching any known ligature sequence
_LIGATURE_REGEX = re.compile(
    "|".join(re.escape(pat) for pat in sorted(LIGATURE_PATTERNS, key=len, reverse=True))
)


def find_ligatures(text: str) -> list[tuple[int, int, str]]:
    """Return all ligature matches in `text` as `(start_index, end_index, match_text)`."""
    if not text:
        return []
    return [(m.start(), m.end(), m.group()) for m in _LIGATURE_REGEX.finditer(text)]


def is_ligature(token: str) -> bool:
    """Return True if `token` is a known multi-character programming ligature."""
    return token in LIGATURE_PATTERNS


class TextSegment:
    """A segment of contiguous cells sharing style, URL, and ligature shaping policy."""

    __slots__ = ("end_col", "is_ligature", "start_col", "style", "text", "url")

    def __init__(
        self,
        start_col: int,
        end_col: int,
        text: str,
        style: Style,
        url: str | None = None,
        is_ligature: bool = False,
    ) -> None:
        self.start_col = start_col
        self.end_col = end_col
        self.text = text
        self.style = style
        self.url = url
        self.is_ligature = is_ligature

    @property
    def width(self) -> int:
        return self.end_col - self.start_col

    def __repr__(self) -> str:
        return (
            f"TextSegment({self.start_col}..{self.end_col}, text={self.text!r}, "
            f"ligature={self.is_ligature})"
        )


def segment_row_cells(
    row_cells: list[Cell],
    cols: int,
    enable_ligatures: bool = True,
) -> list[TextSegment]:
    """Segment a row of cells into styled chunks with ligature alignment preserved."""
    segments: list[TextSegment] = []
    col = 0

    while col < cols:
        cell = row_cells[col]
        if cell.width == 0:
            col += 1
            continue

        st = cell.style
        url = cell.url

        if cell.width == 2:
            segments.append(
                TextSegment(
                    start_col=col,
                    end_col=min(cols, col + 2),
                    text=cell.char,
                    style=st,
                    url=url,
                    is_ligature=False,
                )
            )
            col = min(cols, col + 2)
            continue

        # Gather contiguous identical-style single-width cells
        span_chars = [cell.char]
        next_col = col + 1
        while next_col < cols:
            nc = row_cells[next_col]
            if nc.width == 1 and nc.style == st and nc.url == url:
                span_chars.append(nc.char)
                next_col += 1
            else:
                break

        span_text = "".join(span_chars)
        span_start = col
        span_end = next_col
        col = next_col

        if not enable_ligatures or not span_text.strip():
            segments.append(
                TextSegment(
                    start_col=span_start,
                    end_col=span_end,
                    text=span_text,
                    style=st,
                    url=url,
                    is_ligature=False,
                )
            )
            continue

        # Scan for ligatures within this styled span
        lig_matches = find_ligatures(span_text)
        if not lig_matches:
            segments.append(
                TextSegment(
                    start_col=span_start,
                    end_col=span_end,
                    text=span_text,
                    style=st,
                    url=url,
                    is_ligature=False,
                )
            )
            continue

        # Split span into non-ligature and ligature sub-segments
        curr_idx = 0
        for m_start, m_end, lig_str in lig_matches:
            if m_start > curr_idx:
                prefix = span_text[curr_idx:m_start]
                segments.append(
                    TextSegment(
                        start_col=span_start + curr_idx,
                        end_col=span_start + m_start,
                        text=prefix,
                        style=st,
                        url=url,
                        is_ligature=False,
                    )
                )
            segments.append(
                TextSegment(
                    start_col=span_start + m_start,
                    end_col=span_start + m_end,
                    text=lig_str,
                    style=st,
                    url=url,
                    is_ligature=True,
                )
            )
            curr_idx = m_end

        if curr_idx < len(span_text):
            suffix = span_text[curr_idx:]
            segments.append(
                TextSegment(
                    start_col=span_start + curr_idx,
                    end_col=span_end,
                    text=suffix,
                    style=st,
                    url=url,
                    is_ligature=False,
                )
            )

    return segments
