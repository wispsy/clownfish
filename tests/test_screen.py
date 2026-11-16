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


def test_screen_resize_reflow_narrow_then_widen_preserves_text():
    """Verify 80 -> 20 -> 80 non-destructive reflow."""
    screen = ScreenBuffer(cols=80, rows=24)
    # Write a 45-character line that will wrap when narrowed to 20
    text = "The quick brown fox jumps over the lazy dog."
    for c in text:
        screen.put_char(c)

    assert "".join(c.char for c in screen.grid[0][: len(text)]) == text

    # Narrow to 20 columns: should wrap into 3 rows
    screen.resize(20, 24)
    row0 = "".join(c.char for c in screen.grid[0])
    row1 = "".join(c.char for c in screen.grid[1])
    row2 = "".join(c.char for c in screen.grid[2]).rstrip()
    combined_narrow = row0 + row1 + row2
    assert combined_narrow == text

    # Widen back to 80 columns: text must un-wrap back into single row without data loss
    screen.resize(80, 24)
    row0_wide = "".join(c.char for c in screen.grid[0]).rstrip()
    assert row0_wide == text


def test_screen_resize_height_preserves_scrollback_and_cursor():
    """Verify 24 -> 8 -> 24 row resizing preserves history."""
    screen = ScreenBuffer(cols=40, rows=24)
    for i in range(20):
        for c in f"Line {i:02d}":
            screen.put_char(c)
        screen.cursor_y += 1
        screen.cursor_x = 0

    assert screen.cursor_y == 20

    # Shrink rows to 8
    screen.resize(40, 8)
    assert screen.rows == 8
    assert len(screen.scrollback) > 0

    # Expand rows back to 24
    screen.resize(40, 24)
    assert screen.rows == 24
    # All lines accessible
    visible_texts = ["".join(c.char for c in row).rstrip() for row in screen.grid]
    assert any("Line 00" in t for t in visible_texts) or any("Line 00" in "".join(c.char for c in r) for r in screen.scrollback)


def test_screen_resize_wide_characters_no_split():
    """Verify reflow with CJK and emojis preserves wide character pairs."""
    screen = ScreenBuffer(cols=30, rows=10)
    text = "Status: 🚀 Rocket & 🌟 Star & 世界"
    for c in text:
        screen.put_char(c)

    # Shrink to 12 columns
    screen.resize(12, 10)
    for r in screen.grid:
        for i, cell in enumerate(r):
            if cell.width == 2:
                # Next cell must be spacer
                assert i + 1 < len(r)
                assert r[i + 1].width == 0

    # Widen back to 40 columns
    screen.resize(40, 10)
    wide_text = "".join(c.char for c in screen.grid[0] if c.width != 0).rstrip()
    assert wide_text == text


def test_screen_widen_scrollback_no_index_error():
    """Verify widening terminal and scrolling into scrollback causes no IndexError."""
    screen = ScreenBuffer(cols=20, rows=5)
    for i in range(15):
        for c in f"Message {i}":
            screen.put_char(c)
        screen.scroll_up(1)

    assert len(screen.scrollback) > 0

    # Widen to 100 columns
    screen.resize(100, 10)
    screen.scroll_view(5)  # Scroll up into history

    # Inspect all visible rows up to new column width
    for r in range(screen.rows):
        row = screen.get_visible_row(r)
        assert len(row) >= 100
        # Access each column without IndexError
        _ = row[99]



