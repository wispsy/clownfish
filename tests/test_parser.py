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


def test_parser_colon_separated_sgr():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # Colon-separated TrueColor RGB with optional color space ID (38:2::r:g:bm)
    parser.feed("\x1b[38:2::200:100:50mX\x1b[0m")
    assert screen.grid[0][0].char == "X"
    assert screen.grid[0][0].style.fg == (200, 100, 50)

    # Colon-separated TrueColor RGB without color space ID (38:2:r:g:bm)
    parser.feed("\x1b[38:2:120:60:30mY\x1b[0m")
    assert screen.grid[0][1].char == "Y"
    assert screen.grid[0][1].style.fg == (120, 60, 30)

    # Colon-separated 256 indexed color (38:5:196m)
    parser.feed("\x1b[38:5:196mZ\x1b[0m")
    assert screen.grid[0][2].char == "Z"
    assert screen.grid[0][2].style.fg == (255, 0, 0)


def test_parser_dcs_apc_pm_sos_discarded():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # DCS sequence terminated with ST (\x1b\)
    parser.feed("\x1bP+q1234\x1b\\A")
    # APC sequence terminated with BEL (\x07)
    parser.feed("\x1b_G12345\x07B")
    # PM sequence terminated with ST
    parser.feed("\x1b^privacy\x1b\\C")
    # SOS sequence terminated with ST
    parser.feed("\x1bXstart-of-string\x1b\\D")

    # Only A, B, C, D should have been written to grid
    assert "".join(c.char for c in screen.grid[0][:4]) == "ABCD"


def test_parser_osc_payload_capped():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # Stream oversized OSC payload
    parser.feed("\x1b]")
    parser.feed("A" * 10000)
    assert len(parser.osc_payload) == VT100Parser.MAX_OSC_LENGTH


def test_parser_csi_intermediate_bytes():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # DECSCUSR cursor shape: CSI 1 SP q (SP is 0x20 intermediate byte)
    parser.feed("\x1b[1 qOk")
    assert "".join(c.char for c in screen.grid[0][:2]) == "Ok"


def test_parser_csi_3_j():
    screen = ScreenBuffer(cols=10, rows=3)
    parser = VT100Parser(screen)

    parser.feed("A\r\n\r\n\r\n")  # scrolls A into scrollback
    assert len(screen.scrollback) > 0

    # CSI 3 J clears scrollback
    parser.feed("\x1b[3J")
    assert len(screen.scrollback) == 0


def test_parser_sgr_semicolon_rgb_with_subsequent_attribute():
    screen = ScreenBuffer(cols=20, rows=10)
    parser = VT100Parser(screen)

    # Standard semicolon RGB followed by bold: 38;2;0;255;0;1m
    parser.feed("\x1b[38;2;0;255;0;1mGreenBold\x1b[0m")
    cell = screen.grid[0][0]
    assert cell.char == "G"
    assert cell.style.fg == (0, 255, 0)
    assert cell.style.bold is True

    # Colon-separated RGB followed by bold: 38:2::0:255:0;1m
    screen.move_cursor(1, 0)
    parser.feed("\x1b[38:2::0;255;0;1mAltGreenBold\x1b[0m")
    cell2 = screen.grid[1][0]
    assert cell2.char == "A"
    assert cell2.style.bold is True


