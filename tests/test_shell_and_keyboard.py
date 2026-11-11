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


def test_prompt_navigation_and_alt_screen_preservation():
    screen = ScreenBuffer(cols=40, rows=10)
    parser = VT100Parser(screen)

    # Prompt 1 at row 0
    parser.feed("\x1b]133;A\x1b\\prompt1$ ")
    assert screen.prompt_markers[0].row == 0

    # Output lines causing 5 scroll-ups
    for _ in range(5):
        screen.scroll_up(1)
    assert screen.total_lines_scrolled == 5
    assert len(screen.scrollback) == 5

    # Prompt 2 at cursor row (say, row 3 -> absolute row 5 + 3 = 8)
    screen.move_cursor(row=3, col=0)
    parser.feed("\x1b]133;A\x1b\\prompt2$ ")
    assert screen.prompt_markers[1].row == 8

    # Alternate screen does not wipe prompt markers
    screen.enter_alt_screen()
    assert len(screen.prompt_markers) == 2
    screen.exit_alt_screen()
    assert len(screen.prompt_markers) == 2

    # Prompt jumping:
    # At live view, view top is total_lines_scrolled (5).
    # Jump backwards (-1): should target Prompt 1 (row 0).
    jump_offset = screen.get_prompt_jump_offset(-1)
    assert jump_offset == 5  # total_lines_scrolled(5) - 0 = 5

    # Simulate scrolling to that offset
    screen.scroll_offset = jump_offset
    # Now view top is 5 - 5 = 0.
    # Jump forward (+1): should target Prompt 2 (row 8).
    jump_forward = screen.get_prompt_jump_offset(1)
    assert jump_forward == 0  # row 8 > total_lines_scrolled(5), so clamps to live screen (0)


def test_kitty_keyboard_key_encoding():
    from clownfish.models import encode_kitty_key

    # Unmodified keys return None (handled by standard keymap)
    assert encode_kitty_key("Return", 0) is None
    assert encode_kitty_key("Tab", 0) is None

    # Shift (state 0x1): mod = 1 + 1 = 2
    assert encode_kitty_key("Return", 0x1) == b"\x1b[13;2u"
    assert encode_kitty_key("Tab", 0x1) == b"\x1b[9;2u"
    assert encode_kitty_key("BackSpace", 0x1) == b"\x1b[127;2u"
    assert encode_kitty_key("Escape", 0x1) == b"\x1b[27;2u"

    # Alt/Option (state 0x8): mod = 1 + 2 = 3
    assert encode_kitty_key("Return", 0x8) == b"\x1b[13;3u"

    # Control (state 0x4): mod = 1 + 4 = 5
    assert encode_kitty_key("Return", 0x4) == b"\x1b[13;5u"
    assert encode_kitty_key("BackSpace", 0x4) == b"\x1b[127;5u"

    # Shift + Ctrl (state 0x5): mod = 1 + 1 + 4 = 6
    assert encode_kitty_key("Return", 0x5) == b"\x1b[13;6u"

    # Control + key character (e.g. 'c', state 0x4)
    assert encode_kitty_key("c", 0x4, "c") == b"\x1b[99;5u"

