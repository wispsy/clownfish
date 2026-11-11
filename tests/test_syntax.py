"""Unit tests for Clownfish syntax highlighting using escape-colors."""

from clownfish.screen import ScreenBuffer
from clownfish.syntax import highlight_code, print_highlighted


def test_highlight_code_basic():
    code = "def add(a, b): return a + b"
    ansi_text = highlight_code(code, language="python")
    # Verify that ANSI escape codes are embedded in the output
    assert "\x1b[" in ansi_text
    assert "add" in ansi_text
    assert "return" in ansi_text


def test_print_highlighted_into_screen_buffer():
    screen = ScreenBuffer(cols=40, rows=5)
    code = "x = 42"
    print_highlighted(screen, code, language="python")

    # Verify that text is placed on the screen grid
    row_text = "".join(cell.char for cell in screen.grid[0] if cell.width > 0).rstrip()
    assert row_text == "x = 42"

    # Verify that cells received styling from escape-colors
    # In 'x = 42', number 42 has a distinct fg style (magenta ANSI / extended color)
    digit_cell = screen.grid[0][4]  # '4'
    assert digit_cell.char == "4"
    assert digit_cell.style.fg != ScreenBuffer.ANSI_16[7]  # Not default plain text fg


def test_highlight_code_with_theme():
    code = "class Greeter: pass"
    ansi_default = highlight_code(code, language="python", theme="default")
    ansi_monokai = highlight_code(code, language="python", theme="monokai")
    assert "\x1b[" in ansi_default
    assert "\x1b[" in ansi_monokai
