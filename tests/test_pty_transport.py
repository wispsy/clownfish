"""Tests for PTYTransport."""

from __future__ import annotations

import sys
import time

from clownfish.transports.pty import PTYTransport


def test_pty_transport_live_execution() -> None:
    received = bytearray()
    closed = False

    def on_data(data: bytes) -> None:
        received.extend(data)

    def on_close() -> None:
        nonlocal closed
        closed = True

    cmd = [sys.executable, "-c", "import sys; sys.stdout.write('PTY_WORKS\\n'); sys.stdout.flush()"]
    transport = PTYTransport(
        command=cmd,
        cols=80,
        rows=24,
        on_data=on_data,
        on_close=on_close,
    )

    transport.start()
    assert transport.pid is not None
    assert transport.master_fd is not None

    transport.resize(100, 30)
    assert transport.cols == 100
    assert transport.rows == 30

    # Wait for output
    start_time = time.time()
    while b"PTY_WORKS" not in received and time.time() - start_time < 3.0:
        time.sleep(0.05)

    assert b"PTY_WORKS" in received

    # Wait for close or close transport
    start_time = time.time()
    while transport.is_alive() and time.time() - start_time < 2.0:
        time.sleep(0.05)

    transport.close()
    assert not transport.is_alive()
