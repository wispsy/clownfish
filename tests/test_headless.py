"""Behavioral tests for HeadlessTerminal and headless CLI command execution."""

from __future__ import annotations

import io
import subprocess
import time
from unittest.mock import patch

import pytest

from clownfish import CommandResult, HeadlessTerminal, main
from clownfish.transports.pty import PTYTransport


def test_command_result_str_subclass() -> None:
    """Verify CommandResult behaves both as a string and structured result."""
    cr = CommandResult("hello world\n", command="echo hello world", exit_code=0)
    assert isinstance(cr, str)
    assert "hello" in cr
    assert cr.command == "echo hello world"
    assert cr.exit_code == 0
    assert cr.strip() == "hello world"


def test_headless_terminal_live_execution() -> None:
    """Verify HeadlessTerminal launches session and captures output in buffer."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        assert term.is_alive()
        term.send_input("echo HEADLESS_OK\n")
        assert term.wait_for_text("HEADLESS_OK", timeout=5.0) is True
        text = term.get_text()
        assert "HEADLESS_OK" in text


def test_headless_terminal_line_indexing() -> None:
    """Verify get_line returns exact row contents and validates bounds."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.send_input("echo ROW_INDEX_TEST\n")
        assert term.wait_for_text("ROW_INDEX_TEST", timeout=5.0) is True

        found = False
        for r in range(24):
            line = term.get_line(r)
            if "ROW_INDEX_TEST" in line:
                found = True
                break
        assert found, "Expected ROW_INDEX_TEST in at least one terminal row"

        with pytest.raises(IndexError):
            term.get_line(25)


def test_headless_scrollback_iteration_fix() -> None:
    """Verify get_text(include_scrollback=True) handles Row list iteration safely."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.drain()
        for i in range(30):
            term.session.feed_text(f"line_{i}\r\n")
        term.drain()

        assert len(term.session.screen.scrollback) > 0
        full_text = term.get_text(include_scrollback=True)
        assert "line_0" in full_text
        assert "line_29" in full_text


def test_headless_fresh_prompt_wait_sequence() -> None:
    """Verify wait_for_prompt() tracks prompt sequence numbers and distinguishes fresh prompts."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.session.feed_text("user@host:~$ \x1b]133;A\x07")
        assert term.wait_for_prompt(timeout=0.5) is True

        # Second prompt
        term.session.feed_text("ls\r\n\x1b]133;C\x07output\r\n\x1b]133;D;0\x07\x1b]133;A\x07user@host:~$ ")
        assert term.wait_for_prompt(timeout=0.5) is True


def test_headless_run_command_sentinel_and_exit_code() -> None:
    """Verify run_command returns command-only output and captures exit code."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        # First command
        res1 = term.run_command("echo CLOWNFISH_TOKEN_1", timeout=5.0)
        assert isinstance(res1, CommandResult)
        assert res1.exit_code == 0
        assert "CLOWNFISH_TOKEN_1" in res1
        assert res1.strip() == "CLOWNFISH_TOKEN_1"

        # Second command: verify previous command output is not returned
        res2 = term.run_command("echo CLOWNFISH_TOKEN_2", timeout=5.0)
        assert res2.exit_code == 0
        assert "CLOWNFISH_TOKEN_2" in res2
        assert "CLOWNFISH_TOKEN_1" not in res2
        assert res2.strip() == "CLOWNFISH_TOKEN_2"

        # Non-zero exit code capture
        res3 = term.run_command("sh -c 'exit 42'", timeout=5.0)
        assert res3.exit_code == 42
        assert res3.strip() == ""

        # Check=True should raise CalledProcessError
        with pytest.raises(subprocess.CalledProcessError) as exc_info:
            term.run_command("sh -c 'exit 15'", timeout=5.0, check=True)
        assert exc_info.value.returncode == 15


def test_headless_run_command_non_sentinel() -> None:
    """Verify run_command(use_sentinel=False) waits for prompt and returns pure command output."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        res = term.run_command("echo NON_SENTINEL_OUTPUT", timeout=5.0, use_sentinel=False)
        assert isinstance(res, CommandResult)
        assert res.exit_code == 0
        assert res.strip() == "NON_SENTINEL_OUTPUT"


def test_headless_run_command_timeout() -> None:
    """Verify run_command raises TimeoutError when command exceeds timeout."""
    with (
        HeadlessTerminal(cols=80, rows=24) as term,
        pytest.raises(TimeoutError, match="timed out"),
    ):
        term.run_command("sleep 5", timeout=0.1)


def test_headless_wait_for_prompt_no_premature_return() -> None:
    """Verify repeated wait_for_prompt calls do not prematurely return on stale prompt."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.wait_for_prompt(timeout=2.0)
        # Immediate subsequent wait without sending input should time out
        assert term.wait_for_prompt(timeout=0.05) is False


def test_headless_wait_for_prompt_active_cursor_line() -> None:
    """Verify fallback wait_for_prompt ignores historical prompt symbols in running command output."""
    with HeadlessTerminal(cols=80, rows=24) as term:
        term.wait_for_prompt(timeout=3.0)
        term.drain()

        start_time = time.monotonic()
        # Output prompt-like symbols ($ and >) while sleeping to simulate command output
        term.send_input("echo 'output with $ and >'; sleep 0.4\n")
        ok = term.wait_for_prompt(timeout=5.0)
        lines_dump = [f"{r}: {term.get_line(r)!r}" for r in range(min(12, term.session.rows))]
        assert ok is True, (
            f"Failed wait_for_prompt! cursor={term.cursor_position}\n" + "\n".join(lines_dump)
        )
        elapsed = time.monotonic() - start_time
        # Must have waited for the sleep rather than returning early on 'output with $ and >'
        assert elapsed >= 0.35


def test_cli_command_execution_headless() -> None:
    """Verify clownfish -c executes command and streams output."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["-c", "echo CLOWNFISH_CLI_C_TEST"])
    output = stdout_buf.getvalue()
    assert "CLOWNFISH_CLI_C_TEST" in output


def test_cli_command_runner_headless() -> None:
    """Verify clownfish -c runs via _run_command_headless and exits with code."""
    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf):
        main(["-c", "echo CLI_RUN_063"])
    assert "CLI_RUN_063" in stdout_buf.getvalue()


def test_headless_cli_reader_eof_flush_and_cleanup() -> None:
    """Verify _run_command_headless joins reader thread and cleanly closes transport on exit."""
    from clownfish import _run_command_headless

    closed = False
    original_close = PTYTransport.close

    def tracking_close(self: PTYTransport) -> None:
        nonlocal closed
        closed = True
        original_close(self)

    stdout_buf = io.StringIO()
    with patch("sys.stdout", stdout_buf), patch.object(PTYTransport, "close", tracking_close):
        code = _run_command_headless("echo EOF_FLUSH_TEST && exit 0")

    assert code == 0
    assert "EOF_FLUSH_TEST" in stdout_buf.getvalue()
    assert closed is True
