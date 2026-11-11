"""Tests for TerminalSession and Transport abstraction."""

from __future__ import annotations

import clownfish
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport
from clownfish.transports.ssh import SSHTransport


class MemoryTransport(Transport):
    """In-memory mock transport for testing TerminalSession."""

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.closed = False
        self.written_bytes: list[bytes] = []
        self.dimensions: tuple[int, int] = (80, 24)

    def start(self) -> None:
        self.started = True

    def write(self, data: bytes) -> None:
        self.written_bytes.append(data)

    def resize(self, cols: int, rows: int) -> None:
        self.dimensions = (cols, rows)

    def close(self) -> None:
        self.closed = True
        if self._on_close:
            self._on_close()

    def is_alive(self) -> bool:
        return self.started and not self.closed

    def simulate_incoming(self, data: bytes) -> None:
        """Deliver data as if received from remote peer."""
        if self._on_data:
            self._on_data(data)


def test_session_initialization() -> None:
    transport = MemoryTransport()
    session = TerminalSession(cols=100, rows=30, transport=transport, title="my-term")

    assert session.cols == 100
    assert session.rows == 30
    assert session.title == "my-term"
    assert session.screen.cols == 100
    assert session.screen.rows == 30

    session.start()
    assert transport.started
    assert session.is_alive()


def test_session_feed_and_screen_update() -> None:
    transport = MemoryTransport()
    output_notified = False

    def on_output() -> None:
        nonlocal output_notified
        output_notified = True

    session = TerminalSession(cols=80, rows=24, transport=transport, on_output=on_output)
    session.start()

    # Feed text directly
    session.feed_text("Hello Clownfish!\r\n")
    row_text = "".join(c.char for c in session.screen.get_visible_row(0)).rstrip()
    assert row_text == "Hello Clownfish!"
    assert output_notified

    # Feed byte stream via transport
    transport.simulate_incoming(b"Second line")
    row_1 = "".join(c.char for c in session.screen.get_visible_row(1)).rstrip()
    assert row_1 == "Second line"


def test_session_user_write_and_keys() -> None:
    transport = MemoryTransport()
    session = TerminalSession(transport=transport)
    session.start()

    session.write(b"ls -la\r")
    assert transport.written_bytes[-1] == b"ls -la\r"

    # Send key Return
    session.send_key(keysym="Return")
    assert transport.written_bytes[-1] == b"\r"

    # Send key Up arrow
    session.send_key(keysym="Up")
    assert transport.written_bytes[-1] == b"\x1b[A"

    # Send Ctrl+C
    session.send_key(keysym="c", state=0x4)
    assert transport.written_bytes[-1] == b"\x03"


def test_session_mouse_reporting() -> None:
    transport = MemoryTransport()
    session = TerminalSession(transport=transport)
    session.start()

    # Without mouse tracking enabled, send_mouse returns False
    assert not session.send_mouse(button=0, col=5, row=10, release=False)

    # Enable SGR mouse tracking: CSI ? 1000 h and CSI ? 1006 h
    session.feed_text("\x1b[?1000h\x1b[?1006h")
    assert session.parser.mouse_tracking
    assert session.parser.sgr_mouse_mode

    sent = session.send_mouse(button=0, col=5, row=10, release=False)
    assert sent
    # SGR coordinates are 1-based: col 5 -> 6, row 10 -> 11
    assert transport.written_bytes[-1] == b"\x1b[<0;6;11M"

    # Mouse release
    session.send_mouse(button=0, col=5, row=10, release=True)
    assert transport.written_bytes[-1] == b"\x1b[<0;6;11m"


def test_session_paste_bracketed_and_plain() -> None:
    transport = MemoryTransport()
    session = TerminalSession(transport=transport)
    session.start()

    # Plain paste
    session.paste("foo\nbar")
    assert transport.written_bytes[-1] == b"foo\rbar"

    # Enable bracketed paste: CSI ? 2004 h
    session.feed_text("\x1b[?2004h")
    assert session.parser.bracketed_paste_mode

    session.paste("echo test\n")
    assert transport.written_bytes[-1] == b"\x1b[200~echo test\r\x1b[201~"


def test_session_resize_and_clear() -> None:
    transport = MemoryTransport()
    session = TerminalSession(cols=80, rows=24, transport=transport)
    session.start()

    session.feed_text("Sample data")
    session.resize(cols=120, rows=40)

    assert session.cols == 120
    assert session.rows == 40
    assert session.screen.cols == 120
    assert session.screen.rows == 40
    assert transport.dimensions == (120, 40)

    session.clear()
    assert session.screen.cursor_x == 0
    assert session.screen.cursor_y == 0
    assert len(session.screen.scrollback) == 0


def test_session_close() -> None:
    transport = MemoryTransport()
    closed = False

    def on_close() -> None:
        nonlocal closed
        closed = True

    session = TerminalSession(transport=transport, on_close=on_close)
    session.start()
    assert session.is_alive()

    session.close()
    assert not session.is_alive()
    assert closed


def test_ssh_transport_command_builder() -> None:
    ssh_trans = SSHTransport(
        host="example.com",
        port=2222,
        user="testuser",
        identity_file="/path/to/key",
        extra_args=["-o", "StrictHostKeyChecking=no"],
    )
    cmd = ssh_trans._build_ssh_command()
    assert cmd == [
        "ssh",
        "-tt",
        "-p",
        "2222",
        "-l",
        "testuser",
        "-i",
        "/path/to/key",
        "-o",
        "StrictHostKeyChecking=no",
        "example.com",
    ]


def test_session_event_queue_and_notifier() -> None:
    transport = MemoryTransport()
    notified_count = 0

    def notifier() -> None:
        nonlocal notified_count
        notified_count += 1

    session = TerminalSession(transport=transport)
    session.set_event_notifier(notifier)
    session.start()

    transport.simulate_incoming(b"Queued data")
    assert notified_count == 1
    # Before draining, screen row is blank
    assert "".join(c.char for c in session.screen.get_visible_row(0)).strip() == ""

    session.drain_events()
    assert "".join(c.char for c in session.screen.get_visible_row(0)).strip() == "Queued data"


def test_default_transport_factory() -> None:
    from clownfish.session.session import (
        get_default_transport,
        set_default_transport_factory,
    )

    custom_transport = MemoryTransport()
    set_default_transport_factory(lambda c, r: custom_transport)
    try:
        t = get_default_transport(80, 24)
        assert t is custom_transport
    finally:
        set_default_transport_factory(None)


def test_public_exports() -> None:
    assert hasattr(clownfish, "TerminalSession")
    assert hasattr(clownfish, "Transport")
    assert hasattr(clownfish, "PTYTransport")
    assert hasattr(clownfish, "SSHTransport")
    assert hasattr(clownfish, "TerminalConfig")
    assert clownfish.__version__ == "0.4.0"
