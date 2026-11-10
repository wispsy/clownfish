"""Unit tests for Unicode wide characters, CJK, and emoji grid spacing."""

from clownfish.models import char_width
from clownfish.screen import ScreenBuffer


def test_char_width_classification():
    # ASCII / Latin
    assert char_width("A") == 1
    assert char_width("1") == 1
    assert char_width(" ") == 1

    # CJK Wide characters
    assert char_width("你") == 2
    assert char_width("好") == 2
    assert char_width("世") == 2
    assert char_width("界") == 2

    # Emojis (Wide)
    assert char_width("🚀") == 2
    assert char_width("🔥") == 2

    # Zero-width / combining marks
    assert char_width("\u200d") == 0  # ZWJ
    assert char_width("\ufe0f") == 0  # Variation selector
    assert char_width("\u0301") == 0  # Combining acute accent


def test_wide_character_cell_placement_and_spacer():
    screen = ScreenBuffer(cols=10, rows=5)
    screen.put_char("你")

    # Leading cell at col 0
    cell0 = screen.grid[0][0]
    assert cell0.char == "你"
    assert cell0.width == 2

    # Spacer cell at col 1
    cell1 = screen.grid[0][1]
    assert cell1.char == ""
    assert cell1.width == 0

    # Cursor advances by 2
    assert screen.cursor_x == 2
    assert screen.cursor_y == 0


def test_wide_character_row_boundary_wrap():
    screen = ScreenBuffer(cols=5, rows=3)
    # Move cursor to last column (col 4)
    screen.move_cursor(row=0, col=4)
    screen.put_char("🚀")

    # Col 4 was too small for 2 columns; wrapped to row 1, col 0
    assert screen.grid[0][4].char == " "
    assert screen.grid[1][0].char == "🚀"
    assert screen.grid[1][0].width == 2
    assert screen.grid[1][1].char == ""
    assert screen.grid[1][1].width == 0
    assert screen.cursor_x == 2
    assert screen.cursor_y == 1


def test_overwriting_spacer_cell_resets_leader():
    screen = ScreenBuffer(cols=10, rows=3)
    screen.put_char("你")  # cols 0 & 1
    # Move back to spacer cell at col 1 and write ASCII 'x'
    screen.move_cursor(row=0, col=1)
    screen.put_char("x")

    # Leader at col 0 should be blanked out to prevent corrupted wide glyph
    assert screen.grid[0][0].char == " "
    assert screen.grid[0][0].width == 1
    assert screen.grid[0][1].char == "x"
    assert screen.grid[0][1].width == 1


def test_combining_character_attaches_to_previous_cell():
    screen = ScreenBuffer(cols=10, rows=3)
    screen.put_char("e")
    screen.put_char("\u0301")  # Combining acute accent

    assert screen.grid[0][0].char == "e\u0301"
    assert screen.cursor_x == 1
