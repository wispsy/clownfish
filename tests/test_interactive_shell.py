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


def test_session_thread_safety_no_auto_drain() -> None:
    """Verify that when auto_drain=False, incoming data is not drained on reader thread."""
    class DummyTransport:
        def __init__(self) -> None:
            self.on_data = None
        def set_callbacks(self, on_data=None, on_close=None):
            self.on_data = on_data
        def start(self): pass
        def write(self, data: bytes): pass
        def resize(self, cols: int, rows: int): pass
        def close(self): pass
        def is_alive(self): return True

    transport = DummyTransport()
    session = TerminalSession(transport=transport, auto_drain=False)
    session.start()

    # Simulate data arriving from background thread
    assert transport.on_data is not None
    transport.on_data(b"DelayedText\r\n")

    # Screen must NOT have mutated yet
    assert session.screen.grid[0][0].char == " "
    assert not session._event_queue.empty()

    # Once UI thread explicitly drains, screen updates
    session.drain_events()
    assert session._event_queue.empty()
    assert "".join(c.char for c in session.screen.grid[0][:11]) == "DelayedText"


def test_pty_trampoline_job_control_and_ctty() -> None:
    """Verify that PTYTransport acquires controlling terminal without preexec_fn."""
    import sys

    received = bytearray()
    code = (
        "import os, sys\n"
        "sys.stdout.write(f'CTTY:{os.isatty(0)}\\n')\n"
        "sys.stdout.flush()\n"
    )
    transport = PTYTransport(
        command=[sys.executable, "-c", code],
        cols=80,
        rows=24,
        on_data=lambda d: received.extend(d),
    )
    transport.start()

    deadline = time.time() + 3.0
    while b"CTTY:True" not in received and time.time() < deadline:
        time.sleep(0.05)

    transport.close()
    assert b"CTTY:True" in received
