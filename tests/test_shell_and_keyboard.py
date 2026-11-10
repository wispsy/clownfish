"""Unit tests for OSC 133 semantic shell integration and Kitty keyboard protocol."""

from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer


def test_osc133_prompt_markers_lifecycle():
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen)

    # Shell emits prompt start on row 0
    parser.feed("\x1b]133;A\x1b\\")
    assert len(screen.prompt_markers) == 1
    assert screen.prompt_markers[0].row == 0
    assert screen.prompt_markers[0].exit_code is None

    # Shell emits command execution
    parser.feed("ls -la\r\n\x1b]133;C\x1b\\")

    # Command finishes with exit status 0
    parser.feed("\x1b]133;D;0\x1b\\")
    assert screen.prompt_markers[0].exit_code == 0

    # Next command on row 2 finishes with error code 127
    screen.move_cursor(row=2, col=0)
    parser.feed("\x1b]133;A\x07foo\r\n\x1b]133;C\x07\x1b]133;D;127\x07")
    assert len(screen.prompt_markers) == 2
    assert screen.prompt_markers[1].row == 2
    assert screen.prompt_markers[1].exit_code == 127


def test_kitty_keyboard_protocol_negotiation():
    responses = []
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen, write_response=responses.append)

    # 1. Query initial flags
    parser.feed("\x1b[?u")
    assert responses == [b"\x1b[?0u"]

    # 2. Set flags to 1
    parser.feed("\x1b[=1u")
    assert parser.kitty_keyboard_flags == 1

    # 3. Query updated flags
    responses.clear()
    parser.feed("\x1b[?u")
    assert responses == [b"\x1b[?1u"]

    # 4. Push new flags (3) onto stack
    parser.feed("\x1b[>3u")
    assert parser.kitty_keyboard_flags == 3
    assert parser.kitty_keyboard_stack == [1]

    # 5. Pop flags from stack
    parser.feed("\x1b[<1u")
    assert parser.kitty_keyboard_flags == 1
    assert parser.kitty_keyboard_stack == []
