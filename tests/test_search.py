"""Tests for buffer search."""

from __future__ import annotations

from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.core.search import SearchState, search_screen


def test_search_empty_and_no_match() -> None:
    screen = ScreenBuffer(cols=40, rows=10)
    assert search_screen(screen, "") == []
    assert search_screen(screen, "nonexistent") == []


def test_search_visible_grid_and_case_insensitivity() -> None:
    screen = ScreenBuffer(cols=40, rows=5)
    parser = VT100Parser(screen)
    parser.feed("Hello World! Welcome to clownfish world.\r\n")

    matches = search_screen(screen, "world", case_sensitive=False)
    assert len(matches) == 2
    assert matches[0].start_col == 6
    assert matches[0].end_col == 11
    assert matches[0].text == "World"
    assert not matches[0].is_scrollback

    assert matches[1].start_col == 34
    assert matches[1].end_col == 39
    assert matches[1].text == "world"

    case_matches = search_screen(screen, "World", case_sensitive=True)
    assert len(case_matches) == 1
    assert case_matches[0].text == "World"


def test_search_scrollback_history() -> None:
    screen = ScreenBuffer(cols=30, rows=3)
    parser = VT100Parser(screen)

    # Output lines causing scrollback
    parser.feed("ScrollTarget 1\r\n")
    parser.feed("Line 2\r\n")
    parser.feed("Line 3\r\n")
    parser.feed("ScrollTarget 2\r\n")

    matches = search_screen(screen, "ScrollTarget")
    assert len(matches) == 2
    assert matches[0].is_scrollback is True
    assert matches[0].text == "ScrollTarget"
    assert matches[1].is_scrollback is False


def test_search_regex() -> None:
    screen = ScreenBuffer(cols=40, rows=3)
    parser = VT100Parser(screen)
    parser.feed("User ID: 12345, Session ID: 98765\r\n")

    matches = search_screen(screen, r"\d{5}", regex=True)
    assert len(matches) == 2
    assert matches[0].text == "12345"
    assert matches[1].text == "98765"


def test_search_state_navigation() -> None:
    screen = ScreenBuffer(cols=30, rows=3)
    parser = VT100Parser(screen)
    parser.feed("item1 item2 item3\r\n")

    matches = search_screen(screen, "item")
    state = SearchState()
    assert state.total == 0
    assert state.current_match is None

    state.set_results("item", matches)
    assert state.total == 3
    assert state.current_index == 0
    assert state.current_match is not None
    assert state.current_match.start_col == 0

    # Next match cycles forward
    next_m = state.next_match()
    assert next_m is not None
    assert state.current_index == 1
    assert next_m.start_col == 6

    # Prev match cycles backward
    prev_m = state.prev_match()
    assert prev_m is not None
    assert state.current_index == 0

    # Clear
    state.clear()
    assert state.total == 0
    assert state.current_match is None
