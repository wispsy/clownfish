"""Tests for PTYTransport."""

from __future__ import annotations

import sys
import time

import pytest

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


def test_pty_prespawn_window_size() -> None:
    received = bytearray()

    # Query terminal rows and columns immediately upon process startup
    code = "import fcntl, termios, struct, sys; r, c = struct.unpack('HHHH', fcntl.ioctl(0, termios.TIOCGWINSZ, b'\\0'*8))[:2]; sys.stdout.write(f'SIZE:{c}x{r}\\n'); sys.stdout.flush()"
    cmd = [sys.executable, "-c", code]

    transport = PTYTransport(
        command=cmd,
        cols=112,
        rows=37,
        on_data=lambda d: received.extend(d),
    )
    transport.start()

    start_time = time.time()
    while b"SIZE:112x37" not in received and time.time() - start_time < 3.0:
        time.sleep(0.05)

    transport.close()
    assert b"SIZE:112x37" in received


def test_pty_default_shell_command_args() -> None:
    import os

    env = os.environ.copy()
    env["SHELL"] = "/bin/custom_shell"
    transport = PTYTransport(env=env)

    # When command is None, interactive login shell is prepared
    assert transport.command is None


def test_pty_write_backpressure_and_saturation() -> None:
    """Verify PTYTransport applies backpressure and raises BufferError on saturation timeout."""
    import threading

    transport = PTYTransport(cols=80, rows=24)
    transport._running = True
    transport.master_fd = 999  # Mock valid descriptor

    # Reduce queue limit for deterministic test
    transport.MAX_WRITE_QUEUE_CHUNKS = 3

    # Enqueue up to limit
    transport.write(b"chunk-1")
    transport.write(b"chunk-2")
    transport.write(b"chunk-3")
    assert len(transport._write_queue) == 3

    # Writing when saturated should timeout and raise BufferError
    with pytest.raises(BufferError, match="saturated"):
        transport.write(b"chunk-overflow", timeout=0.05)

    # Draining a chunk should notify condition and allow subsequent write
    def pop_chunk_later() -> None:
        time.sleep(0.05)
        with transport._write_cv:
            transport._write_queue.popleft()
            transport._write_cv.notify()

    t = threading.Thread(target=pop_chunk_later)
    t.start()
    transport.write(b"chunk-recovered", timeout=0.5)
    t.join()
    assert b"chunk-recovered" in transport._write_queue


