"""Headless terminal frontend for non-GUI execution, automation, and testing."""

from __future__ import annotations

import re
import time
from types import TracebackType
from typing import ClassVar, Self

from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport


class CommandResult(str):
    """Structured command execution result subclassing str for full backward compatibility."""

    command: str
    exit_code: int
    output: str

    def __new__(cls, output: str, command: str = "", exit_code: int = 0) -> Self:
        instance = super().__new__(cls, output)
        instance.command = command
        instance.exit_code = exit_code
        instance.output = output
        return instance


class HeadlessTerminal:
    """Programmatic headless terminal interface wrapping TerminalSession.

    Provides a clean, dependency-free API to run shell or SSH sessions, send keystrokes,
    and inspect terminal screen content without any graphical window (Tkinter).
    """

    PROMPT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"[$%#>❯➜→λ»]\s*$")

    def __init__(
        self,
        cols: int = 80,
        rows: int = 24,
        max_scrollback: int = 10_000,
        transport: Transport | None = None,
        cwd: str | None = None,
        title: str = "clownfish-headless",
        auto_drain: bool = False,
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.auto_drain = auto_drain
        self._prompt_marker_index = 0
        self.session = TerminalSession(
            cols=cols,
            rows=rows,
            max_scrollback=max_scrollback,
            transport=transport,
            title=title,
            auto_drain=auto_drain,
            cwd=cwd,
        )

    def start(self) -> Self:
        """Start the session transport."""
        self.session.start()
        return self

    def drain(self, max_bytes: int = 512_000) -> bool:
        """Drain any pending bytes and events from the transport."""
        return self.session.drain_events(max_bytes=max_bytes)

    def send_input(self, text: str) -> None:
        """Send plain text or shell commands into the terminal transport."""
        self.session.write(text.encode("utf-8"))

    def send_key(self, keysym: str, state: int = 0, char: str = "") -> bool:
        """Send a formatted keystroke event into the session."""
        return self.session.send_key(keysym=keysym, state=state, char=char)

    @property
    def cursor_position(self) -> tuple[int, int]:
        """Return the current cursor (col, row) coordinates (0-indexed)."""
        return self.session.screen.cursor_x, self.session.screen.cursor_y

    def get_line(self, row: int, rstrip: bool = True) -> str:
        """Return the text content of a single visible row."""
        if not (0 <= row < self.session.rows):
            raise IndexError(f"Row {row} is out of bounds (0..{self.session.rows - 1})")
        cells = self.session.screen.get_visible_row(row)
        line = "".join(cell.char for cell in cells if cell.width != 0)
        return line.rstrip() if rstrip else line

    def get_text(
        self,
        start_row: int = 0,
        end_row: int | None = None,
        rstrip: bool = True,
        include_scrollback: bool = False,
    ) -> str:
        """Return visible screen lines as a newline-delimited string.

        If `include_scrollback` is True, prepends all saved scrollback lines.
        """
        self.drain()
        lines: list[str] = []

        if include_scrollback:
            for row in self.session.screen.scrollback:
                line_text = "".join(cell.char for cell in row if cell.width != 0)
                lines.append(line_text.rstrip() if rstrip else line_text)

        last_row = self.session.rows if end_row is None else min(self.session.rows, end_row)
        for r in range(start_row, last_row):
            lines.append(self.get_line(r, rstrip=rstrip))

        return "\n".join(lines)

    def wait_for_text(
        self,
        pattern: str | re.Pattern[str],
        timeout: float = 5.0,
        interval: float = 0.05,
        include_scrollback: bool = False,
    ) -> bool:
        """Poll terminal output until `pattern` matches or `timeout` expires.

        `pattern` may be a plain string substring or a compiled regex.
        Returns True if matched, False on timeout.
        """
        regex = re.compile(pattern) if isinstance(pattern, str) else pattern
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            self.drain()
            current_text = self.get_text(include_scrollback=include_scrollback)
            if regex.search(current_text):
                return True
            time.sleep(interval)

        # Final drain check
        self.drain()
        return bool(regex.search(self.get_text(include_scrollback=include_scrollback)))

    def wait_for_prompt(
        self,
        timeout: float = 5.0,
        interval: float = 0.05,
        since_marker: int | None = None,
    ) -> bool:
        """Wait until a new OSC 133 semantic prompt mark or fresh shell prompt appears.

        If `since_marker` is specified, waits until total prompt markers exceed that count.
        Otherwise, tracks the sequence of prompts to ensure repeated waits don't return early.
        """
        baseline = since_marker if since_marker is not None else self._prompt_marker_index
        deadline = time.monotonic() + timeout
        initial_text = self.get_text()
        initial_cursor = self.cursor_position
        initial_abs_cursor = self.session.screen.total_lines_scrolled + self.session.screen.cursor_y

        while time.monotonic() < deadline:
            self.drain()
            current_markers = len(self.session.screen.prompt_markers)
            if current_markers > baseline:
                self._prompt_marker_index = current_markers
                return True

            # If no new OSC 133 marker arrived, check active cursor line for common shell prompt terminators
            cx, cy = self.cursor_position
            cursor_line = self.get_line(cy)
            prefix_to_cursor = cursor_line[:cx].rstrip() if cx > 0 else cursor_line.rstrip()
            has_prompt = bool(
                self.PROMPT_PATTERN.search(prefix_to_cursor)
                or self.PROMPT_PATTERN.search(cursor_line.strip())
            )
            current_abs_cursor = self.session.screen.total_lines_scrolled + cy

            if has_prompt:
                if self._prompt_marker_index == 0 and baseline == 0:
                    self._prompt_marker_index = 1
                    return True
                if (
                    current_abs_cursor > initial_abs_cursor
                    or (
                        current_abs_cursor != initial_abs_cursor
                        and self.get_text() != initial_text
                    )
                    or (
                        self.get_text() != initial_text
                        and (cx, cy) != initial_cursor
                    )
                ):
                    self._prompt_marker_index += 1
                    return True
            time.sleep(interval)

        self.drain()
        current_markers = len(self.session.screen.prompt_markers)
        if current_markers > baseline:
            self._prompt_marker_index = current_markers
            return True
        return False

    def run_command(
        self,
        cmd: str,
        timeout: float = 10.0,
        use_sentinel: bool = True,
        check: bool = False,
    ) -> CommandResult:
        """Execute a shell command, wait for completion, and return only the command's output.

        Args:
            cmd: Shell command string to execute.
            timeout: Maximum seconds to wait before raising TimeoutError.
            use_sentinel: When True, uses a unique command completion token and captures
                the exact process exit code ($?). When False, waits for standard shell prompt.
            check: When True, raises subprocess.CalledProcessError if exit_code != 0.

        Returns:
            CommandResult (subclass of str) containing the captured command output,
            with .exit_code and .command attributes.

        Raises:
            TimeoutError: If the command does not complete within `timeout` seconds.
            subprocess.CalledProcessError: If `check=True` and exit_code is non-zero.
        """
        import subprocess
        import uuid

        if use_sentinel:
            token = f"__CF_{uuid.uuid4().hex[:8]}__"
            sentinel_re = re.compile(rf"{token}:(-?\d+)")
            deadline = time.monotonic() + timeout

            self.drain()
            if self._prompt_marker_index == 0:
                self.wait_for_prompt(timeout=min(2.0, timeout))

            start_abs_line = self.session.screen.total_lines_scrolled + self.session.screen.cursor_y

            if "\n" in cmd.strip():
                formatted_cmd = f"(\n{cmd.strip()}\n); printf \"{token}:%d\\n\" $?\n"
            else:
                formatted_cmd = f"{cmd.rstrip()} ; printf \"{token}:%d\\n\" $?\n"

            self.send_input(formatted_cmd)

            exit_code = 0
            matched_output = ""
            while time.monotonic() < deadline:
                self.drain()
                all_lines = self.get_text(include_scrollback=True).split("\n")
                base_abs_line = self.session.screen.total_lines_scrolled - len(self.session.screen.scrollback)
                start_idx = max(0, start_abs_line - base_abs_line)

                sentinel_idx = None
                for idx in range(start_idx, len(all_lines)):
                    m = sentinel_re.search(all_lines[idx])
                    if m and "printf" not in all_lines[idx] and ";" not in all_lines[idx]:
                        sentinel_idx = idx
                        exit_code = int(m.group(1))
                        break

                if sentinel_idx is not None:
                    cmd_lines = all_lines[start_idx:sentinel_idx]
                    # Locate the end of the input echo (the line containing the printf sentinel command)
                    echo_end_idx = None
                    for i in range(len(cmd_lines) - 1, -1, -1):
                        if token in cmd_lines[i]:
                            echo_end_idx = i
                            break
                    if echo_end_idx is not None:
                        output_lines = cmd_lines[echo_end_idx + 1 :]
                    elif cmd_lines and cmd.strip() in cmd_lines[0]:
                        output_lines = cmd_lines[1:]
                    else:
                        output_lines = cmd_lines
                    matched_output = "\n".join(output_lines).strip()
                    break
                time.sleep(0.02)
            else:
                raise TimeoutError(f"Command '{cmd}' timed out after {timeout} seconds")

            self.wait_for_prompt(timeout=0.5)

            if check and exit_code != 0:
                raise subprocess.CalledProcessError(exit_code, cmd, output=matched_output)

            return CommandResult(matched_output, command=cmd, exit_code=exit_code)

        # Fallback non-sentinel execution
        self.drain()
        if self._prompt_marker_index == 0:
            self.wait_for_prompt(timeout=min(2.0, timeout))

        all_before = self.get_text(include_scrollback=True).split("\n")
        base_before = self.session.screen.total_lines_scrolled - len(self.session.screen.scrollback)
        start_abs_line = self.session.screen.total_lines_scrolled + self.session.screen.cursor_y
        cur_idx_before = max(0, start_abs_line - base_before)
        header_before = all_before[:cur_idx_before]

        baseline = len(self.session.screen.prompt_markers)
        self.send_input(cmd.rstrip("\n") + "\n")
        if not self.wait_for_prompt(timeout=timeout, since_marker=baseline):
            raise TimeoutError(f"Command '{cmd}' timed out waiting for prompt after {timeout} seconds")

        all_lines = self.get_text(include_scrollback=True).split("\n")
        base_abs_line = self.session.screen.total_lines_scrolled - len(self.session.screen.scrollback)
        start_idx = max(0, start_abs_line - base_abs_line)
        prompt_idx = max(
            0,
            (self.session.screen.total_lines_scrolled + self.session.screen.cursor_y) - base_abs_line,
        )
        output_lines = all_lines[start_idx:prompt_idx] if prompt_idx >= start_idx else all_lines[start_idx:]
        if output_lines and cmd.strip() in output_lines[0]:
            output_lines = output_lines[1:]
        # Strip matching prompt header lines from bottom of output_lines
        while output_lines and (
            output_lines[-1].strip() == ""
            or any(output_lines[-1].strip() == h.strip() for h in header_before if h.strip())
        ):
            output_lines.pop()
        out = "\n".join(output_lines).strip()
        return CommandResult(out, command=cmd, exit_code=0)

    def is_alive(self) -> bool:
        """Return True if the underlying session transport process is active."""
        return self.session.is_alive()

    def close(self) -> None:
        """Cleanly close the session and its transport."""
        self.session.close()

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
