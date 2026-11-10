"""Unit tests for ScreenBuffer."""

from clownfish.screen import ScreenBuffer


def test_screen_buffer_initialization():
    screen = ScreenBuffer(cols=80, rows=24)
    assert screen.cols == 80
    assert screen.rows == 24
    assert screen.cursor_x == 0
    assert screen.cursor_y == 0
    assert len(screen.grid) == 24
    assert len(screen.grid[0]) == 80


def test_put_char_and_cursor_advance():
    screen = ScreenBuffer(cols=10, rows=5)
    screen.put_char("A")
    assert screen.cursor_x == 1
    assert screen.cursor_y == 0
    assert screen.grid[0][0].char == "A"


def test_scroll_up_and_scrollback():
    screen = ScreenBuffer(cols=10, rows=3, max_scrollback=5)
    screen.put_char("1")
    screen.cursor_y = 2
    screen.scroll_up(1)

    assert len(screen.scrollback) == 1
    assert screen.scrollback[0][0].char == "1"


def test_alt_screen_toggle():
    screen = ScreenBuffer(cols=10, rows=5)
    screen.put_char("P")  # Primary screen
    screen.enter_alt_screen()
    assert screen.is_alt_screen
    assert screen.grid[0][0].char == " "

    screen.put_char("A")  # Alt screen
    assert screen.grid[0][0].char == "A"

    screen.exit_alt_screen()
    assert not screen.is_alt_screen
    assert screen.grid[0][0].char == "P"


def test_erase_in_display():
    screen = ScreenBuffer(cols=5, rows=3)
    screen.put_char("X")
    screen.put_char("Y")
    screen.erase_in_display(2)
    assert screen.grid[0][0].char == " "
    assert screen.grid[0][1].char == " "
