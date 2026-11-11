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


def test_clear_all_resets_grid_and_scrollback():
    screen = ScreenBuffer(cols=10, rows=3, max_scrollback=50)
    screen.put_char("H")
    screen.put_char("i")
    screen.scroll_up(2)
    screen.scroll_view(1)
    assert len(screen.scrollback) > 0
    assert screen.scroll_offset > 0

    screen.clear_all()
    assert len(screen.scrollback) == 0
    assert screen.scroll_offset == 0
    assert screen.cursor_x == 0
    assert screen.cursor_y == 0
    assert all(c.char == " " for row in screen.grid for c in row)
    assert len(screen.dirty_lines) == screen.rows


def test_standard_xterm_256_color_cube():
    # Index 16 should be (0, 0, 0)
    assert ScreenBuffer._index_to_rgb(16) == (0, 0, 0)
    # Index 231 should be (255, 255, 255)
    assert ScreenBuffer._index_to_rgb(231) == (255, 255, 255)
    # Index 196: red (255, 0, 0)
    assert ScreenBuffer._index_to_rgb(196) == (255, 0, 0)
    # Index 46: green (0, 255, 0)
    assert ScreenBuffer._index_to_rgb(46) == (0, 255, 0)
    # Index 21: blue (0, 0, 255)
    assert ScreenBuffer._index_to_rgb(21) == (0, 0, 255)
    # Test intermediate cube level 95 (step index 1)
    # Index 16 + 1*36 = 52 -> (95, 0, 0)
    assert ScreenBuffer._index_to_rgb(52) == (95, 0, 0)
    # Grayscale ramp 232 -> 8, 255 -> 238
    assert ScreenBuffer._index_to_rgb(232) == (8, 8, 8)
    assert ScreenBuffer._index_to_rgb(255) == (238, 238, 238)


def test_csi_3_j_erases_saved_lines_only():
    screen = ScreenBuffer(cols=10, rows=3)
    screen.put_char("A")
    screen.scroll_up(2)
    assert len(screen.scrollback) == 2
    screen.put_char("B")

    # Mode 3 clears scrollback, preserving visible grid
    screen.erase_in_display(3)
    assert len(screen.scrollback) == 0
    assert screen.scroll_offset == 0
    assert screen.grid[0][1].char == "B"


def test_screen_autowrap_pending_state():
    screen = ScreenBuffer(cols=5, rows=3)
    for c in "HELLO":
        screen.put_char(c)

    # After filling the line, cursor should stay on last column (col 4) with wrap_pending
    assert screen.cursor_x == 4
    assert screen.cursor_y == 0
    assert screen.wrap_pending is True

    # Writing next character causes deferred wrap to row 1, col 1
    screen.put_char("!")
    assert screen.cursor_y == 1
    assert screen.cursor_x == 1
    assert screen.wrap_pending is False
    assert screen.grid[1][0].char == "!"



