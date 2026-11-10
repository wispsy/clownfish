"""Unit tests for Primary/Secondary Device Attributes, DSR, and color queries."""

from clownfish.models import DEFAULT_BG, DEFAULT_FG
from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer


def test_primary_device_attributes_reply():
    responses = []
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen, write_response=responses.append)

    parser.feed("\x1b[c")
    assert responses == [b"\x1b[?62;c"]

    responses.clear()
    parser.feed("\x1b[0c")
    assert responses == [b"\x1b[?62;c"]


def test_secondary_device_attributes_reply():
    responses = []
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen, write_response=responses.append)

    parser.feed("\x1b[>c")
    assert responses == [b"\x1b[>1;10;0c"]

    responses.clear()
    parser.feed("\x1b[>0c")
    assert responses == [b"\x1b[>1;10;0c"]


def test_cursor_position_report_and_status():
    responses = []
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen, write_response=responses.append)

    # Position cursor at row 4, col 9 (0-indexed) -> 1-indexed (5, 10)
    screen.move_cursor(row=4, col=9)
    parser.feed("\x1b[6n")
    assert responses == [b"\x1b[5;10R"]

    responses.clear()
    parser.feed("\x1b[5n")
    assert responses == [b"\x1b[0n"]


def test_color_queries_reply():
    responses = []
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen, write_response=responses.append)

    # Query FG with BEL terminator
    parser.feed("\x1b]10;?\x07")
    expected_fg = f"\x1b]10;rgb:{DEFAULT_FG[0]:02x}{DEFAULT_FG[0]:02x}/{DEFAULT_FG[1]:02x}{DEFAULT_FG[1]:02x}/{DEFAULT_FG[2]:02x}{DEFAULT_FG[2]:02x}\x1b\\".encode("ascii")
    assert responses == [expected_fg]

    responses.clear()
    # Query BG with ST terminator
    parser.feed("\x1b]11;?\x1b\\")
    expected_bg = f"\x1b]11;rgb:{DEFAULT_BG[0]:02x}{DEFAULT_BG[0]:02x}/{DEFAULT_BG[1]:02x}{DEFAULT_BG[1]:02x}/{DEFAULT_BG[2]:02x}{DEFAULT_BG[2]:02x}\x1b\\".encode("ascii")
    assert responses == [expected_bg]
