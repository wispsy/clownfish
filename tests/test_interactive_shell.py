"""Tests for interactive shell compatibility, ZLE tab completion, and prompt recovery."""

from __future__ import annotations

import shutil
import time

import pytest

from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.session.session import TerminalSession
from clownfish.transports.pty import PTYTransport


def test_clear_preserves_prompt_via_redraw() -> None:
    """Verify that session.clear(request_redraw=True) requests shell prompt redraw via Ctrl+L."""
    class DummyTransport:
        def __init__(self) -> None:
            self.written: list[bytes] = []
        def set_callbacks(self, on_data=None, on_close=None): pass
        def start(self): pass
        def write(self, data: bytes): self.written.append(data)
        def resize(self, cols: int, rows: int): pass
        def close(self): pass
        def is_alive(self): return True

    transport = DummyTransport()
    session = TerminalSession(transport=transport)
    session.start()

    session.screen.move_cursor(2, 10)
    session.screen.put_char("x")
    session.clear(request_redraw=True)

    assert session.screen.cursor_x == 0
    assert session.screen.cursor_y == 0
    assert len(session.screen.scrollback) == 0
    assert transport.written == [b"\x0c"]


def test_clear_in_alt_screen_does_not_send_ctrl_l() -> None:
    """Verify that session.clear() in alternate screen (e.g. vim) does not emit Ctrl+L."""
    class DummyTransport:
        def __init__(self) -> None:
            self.written: list[bytes] = []
        def set_callbacks(self, on_data=None, on_close=None): pass
        def start(self): pass
        def write(self, data: bytes): self.written.append(data)
        def resize(self, cols: int, rows: int): pass
        def close(self): pass
        def is_alive(self): return True

    transport = DummyTransport()
    session = TerminalSession(transport=transport)
    session.start()

    session.screen.enter_alt_screen()
    session.clear(request_redraw=True)

    assert transport.written == []


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not available on system")
def test_live_zsh_tab_completion_no_stray_prompts() -> None:
    """Test that live zsh connected to PTYTransport does not emit stray '%' prompts on Tab."""
    zsh_path = shutil.which("zsh")
    assert zsh_path is not None

    screen = ScreenBuffer(cols=80, rows=24)
    received = bytearray()

    def on_data(data: bytes) -> None:
        received.extend(data)

    transport = PTYTransport(
        command=[zsh_path, "-l", "-i"],
        cols=80,
        rows=24,
        on_data=on_data,
    )
    transport.start()

    try:
        # Wait for initial prompt to render
        deadline = time.time() + 3.0
        while time.time() < deadline:
            if received:
                break
            time.sleep(0.05)

        # Feed received bytes to parser
        parser = VT100Parser(screen)
        parser.feed(received.decode("utf-8", errors="replace"))
        received.clear()

        # Send a Tab keystroke (plain b"\t")
        transport.write(b"\t")
        time.sleep(0.3)

        # Ensure that no stray `%` was output due to uninitialized geometry
        tab_output = bytes(received)
        # Stray prompt character in uninitialized zsh is "%" followed by 70+ spaces
        assert b"%                                                              " not in tab_output

    finally:
        transport.close()
