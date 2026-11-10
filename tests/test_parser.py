"""Unit tests for VT100Parser."""

from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer


def test_parser_basic_text_and_cursor():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    parser.feed("Hello\r\nWorld")
    assert "".join(c.char for c in screen.grid[0][:5]) == "Hello"
    assert "".join(c.char for c in screen.grid[1][:5]) == "World"
    assert screen.cursor_x == 5
    assert screen.cursor_y == 1


def test_parser_csi_cursor_movement():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # Move cursor to row 5, col 7 (1-based: CSI 5;7H)
    parser.feed("\x1b[5;7H")
    assert screen.cursor_y == 4
    assert screen.cursor_x == 6

    # Move cursor up 2 lines (CSI 2A)
    parser.feed("\x1b[2A")
    assert screen.cursor_y == 2


def test_parser_sgr_styling():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # Set bold and red fg (SGR 1;31m)
    parser.feed("\x1b[1;31mHi\x1b[0m")
    hi_cell = screen.grid[0][0]
    assert hi_cell.char == "H"
    assert hi_cell.style.bold is True
    assert hi_cell.style.fg == ScreenBuffer.ANSI_16[1]
    assert screen.current_style.bold is False


def test_parser_osc8_hyperlink():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # OSC 8 ; ; URL \x1b\ LINK \x1b]8;;\x1b\
    parser.feed("\x1b]8;;https://example.com\x07Link\x1b]8;;\x07")
    cell = screen.grid[0][0]
    assert cell.char == "L"
    assert cell.url == "https://example.com"
    assert screen.current_url is None
