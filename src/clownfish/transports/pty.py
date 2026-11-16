"""Local pseudo-terminal (PTY) transport using thread-safe subprocess spawning."""

from __future__ import annotations

import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
from collections import deque
from collections.abc import Callable

from clownfish.session.transport import Transport


class PTYTransport(Transport):
    """Transport executing a local command or interactive shell inside a PTY."""

    def __init__(
        self,
        command: list[str] | None = None,
        cols: int = 80,
        rows: int = 24,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        on_data: Callable[[bytes], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(on_data=on_data, on_close=on_close)
        self.command = command
        self.cols = cols
        self.rows = rows
        self.env = env
        self.cwd = cwd

        self.pid: int | None = None
        self.master_fd: int | None = None
        self._proc: subprocess.Popen | None = None
        self._running = False
        self._reader_thread: threading.Thread | None = None
        self._write_queue: deque[bytes] = deque()
        self._write_lock = threading.Lock()

    def start(self) -> None:
        """Allocate PTY, spawn child process with start_new_session, and launch reader."""
        if self._running or self.master_fd is not None:
            return

        master_fd, slave_fd = pty.openpty()

        # Set initial terminal dimensions on slave_fd BEFORE spawning the child
        try:
            winsize = struct.pack("HHHH", self.rows, self.cols, self.cols * 8, self.rows * 16)
            fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        if self.env:
            env.update(self.env)

        if self.command:
            cmd = self.command
        else:
            shell = env.get("SHELL") or ("/bin/zsh" if sys.platform == "darwin" else "/bin/bash")
            cmd = [shell, "-l", "-i"]

        if sys.platform != "win32":
            trampoline = (
                "import fcntl, os, sys, termios\n"
                "try:\n"
                "    fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
                "except OSError:\n"
                "    pass\n"
                "os.execvp(sys.argv[1], sys.argv[1:])\n"
            )
            spawn_cmd = [sys.executable, "-c", trampoline, *cmd]
        else:
            spawn_cmd = cmd

        try:
            proc = subprocess.Popen(
                spawn_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.cwd,
                env=env,
                close_fds=True,
                start_new_session=True,
            )
        except OSError:
            os.close(master_fd)
            os.close(slave_fd)
            raise
        finally:
            try:
                os.close(slave_fd)
            except OSError:
                pass

        self._proc = proc
        self.pid = proc.pid
        self.master_fd = master_fd
        self._running = True

        os.set_blocking(self.master_fd, False)
        self.resize(self.cols, self.rows)

        self._reader_thread = threading.Thread(
            target=self._reader_loop, name=f"clownfish-pty-{proc.pid}", daemon=True
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        """Background loop multiplexing reads and buffered writes to the master PTY."""
        while self._running and self.master_fd is not None:
            try:
                fd = self.master_fd
                if fd is None:
                    break

                with self._write_lock:
                    has_writes = bool(self._write_queue)

                wlist_in = [fd] if has_writes else []
                rlist, wlist, _ = select.select([fd], wlist_in, [], 0.05)

                # Process pending writes if descriptor is writable
                if wlist and self.master_fd is not None:
                    with self._write_lock:
                        if self._write_queue:
                            chunk = self._write_queue.popleft()
                            try:
                                written = os.write(self.master_fd, chunk)
                                if written < len(chunk):
                                    self._write_queue.appendleft(chunk[written:])
                            except (BlockingIOError, InterruptedError):
                                self._write_queue.appendleft(chunk)
                            except OSError:
                                break

                # Process incoming reads
                if rlist and self.master_fd is not None:
                    raw_bytes = os.read(self.master_fd, 65536)
                    if not raw_bytes:
                        break
                    if self._on_data:
                        self._on_data(raw_bytes)

            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                break

        self._running = False
        if self._on_close:
            self._on_close()

    def write(self, data: bytes) -> None:
        """Enqueue bytes for lossless asynchronous writing to the master PTY."""
        if not self._running or self.master_fd is None or not data:
            return
        with self._write_lock:
            self._write_queue.append(data)

    def resize(self, cols: int, rows: int) -> None:
        """Update PTY window size."""
        self.cols = cols
        self.rows = rows
        if self.master_fd is None:
            return
        try:
            winsize = struct.pack("HHHH", rows, cols, cols * 8, rows * 16)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def close(self) -> None:
        """Terminate the PTY, clear write queue, and reap the child process."""
        self._running = False
        with self._write_lock:
            self._write_queue.clear()

        fd = self.master_fd
        proc = self._proc
        self.master_fd = None
        self._proc = None
        self.pid = None

        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass

        if proc is not None:
            try:
                proc.send_signal(signal.SIGHUP)
            except OSError:
                pass
            try:
                proc.wait(timeout=0.2)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                    proc.wait(timeout=0.2)
                except OSError:
                    pass

    def is_alive(self) -> bool:
        """Check if child process is alive."""
        if not self._running or self._proc is None:
            return False
        ret = self._proc.poll()
        if ret is not None:
            self._running = False
            return False
        return True
