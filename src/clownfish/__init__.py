"""clownfish - A modern terminal emulator written in Python and Tkinter."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from clownfish.config import TerminalConfig
from clownfish.core.keyboard import encode_key_press, encode_kitty_key
from clownfish.core.models import (
    Cell,
    PromptMarker,
    Selection,
    Style,
    char_width,
)
from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.core.search import SearchMatch, SearchState, search_screen
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport
from clownfish.syntax import highlight_code, is_syntax_available, print_highlighted

if TYPE_CHECKING:
    from clownfish.frontends.headless import HeadlessTerminal
    from clownfish.frontends.tkinter.app import TkTerminalApp
    from clownfish.frontends.tkinter.pane import TerminalPane
    from clownfish.frontends.tkinter.split import SplitView
    from clownfish.frontends.tkinter.tabs import TabbedTerminalView
    from clownfish.transports.pty import PTYTransport
    from clownfish.transports.ssh import SSHTransport

__version__ = "0.6.1"
__all__ = [
    "Cell",
    "HeadlessTerminal",
    "PTYTransport",
    "PromptMarker",
    "SSHTransport",
    "ScreenBuffer",
    "SearchMatch",
    "SearchState",
    "Selection",
    "SplitView",
    "Style",
    "TabbedTerminalView",
    "TerminalConfig",
    "TerminalPane",
    "TerminalSession",
    "TkTerminalApp",
    "Transport",
    "VT100Parser",
    "char_width",
    "encode_key_press",
    "encode_kitty_key",
    "highlight_code",
    "is_syntax_available",
    "main",
    "print_highlighted",
    "search_screen",
]


def __getattr__(name: str) -> Any:
    if name == "HeadlessTerminal":
        from clownfish.frontends.headless import HeadlessTerminal

        return HeadlessTerminal
    if name == "TkTerminalApp":
        from clownfish.frontends.tkinter.app import TkTerminalApp

        return TkTerminalApp
    if name == "TerminalPane":
        from clownfish.frontends.tkinter.pane import TerminalPane

        return TerminalPane
    if name == "SplitView":
        from clownfish.frontends.tkinter.split import SplitView

        return SplitView
    if name == "TabbedTerminalView":
        from clownfish.frontends.tkinter.tabs import TabbedTerminalView

        return TabbedTerminalView
    if name == "PTYTransport":
        from clownfish.transports.pty import PTYTransport

        return PTYTransport
    if name == "SSHTransport":
        from clownfish.transports.ssh import SSHTransport

        return SSHTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _run_headless_bridge(
    transport: Transport | None = None,
    command: str | None = None,
    cols: int = 80,
    rows: int = 24,
) -> int:
    """Stream bidirectional I/O for headless CLI and automated command execution."""
    import os
    import select
    import subprocess
    import sys
    import threading
    import time

    from clownfish.transports.pty import PTYTransport

    if transport is None:
        if command is not None:
            shell = os.environ.get("SHELL") or ("/bin/zsh" if sys.platform == "darwin" else "/bin/bash")
            cmd = [shell, "-c", command]
        else:
            cmd = None
        transport = PTYTransport(command=cmd, cols=cols, rows=rows)

    def on_pty_data(data: bytes) -> None:
        try:
            if hasattr(sys.stdout, "buffer"):
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                sys.stdout.write(data.decode("utf-8", errors="replace"))
                sys.stdout.flush()
        except OSError:
            pass

    transport.set_callbacks(on_data=on_pty_data)
    transport.start()

    stop_event = threading.Event()

    def stdin_forwarder() -> None:
        while not stop_event.is_set() and transport.is_alive():
            try:
                if sys.platform != "win32" and hasattr(sys.stdin, "fileno"):
                    try:
                        rlist, _, _ = select.select([sys.stdin.fileno()], [], [], 0.05)
                        if not rlist:
                            continue
                    except (OSError, ValueError):
                        pass
                if hasattr(sys.stdin, "buffer"):
                    chunk = sys.stdin.buffer.read(4096)
                else:
                    text_chunk = sys.stdin.read(4096)
                    chunk = text_chunk.encode("utf-8") if text_chunk else b""
                if not chunk:
                    break
                transport.write(chunk)
            except (OSError, ValueError):
                break

    if command is None and hasattr(sys.stdin, "read"):
        stdin_thread = threading.Thread(target=stdin_forwarder, daemon=True)
        stdin_thread.start()

    while transport.is_alive():
        time.sleep(0.05)

    stop_event.set()
    exit_code = 0
    if isinstance(transport, PTYTransport) and transport._proc:
        try:
            exit_code = transport._proc.wait(timeout=0.2) or 0
        except (subprocess.TimeoutExpired, OSError):
            exit_code = transport._proc.poll() or 0
    return exit_code


def main(args: list[str] | None = None) -> None:
    """Launch clownfish terminal emulator."""
    import sys

    argv = args if args is not None else sys.argv[1:]
    if argv and argv[0] == "--pty-trampoline":
        import fcntl
        import os
        import termios

        try:
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        except OSError:
            pass
        os.execvp(argv[1], argv[1:])
        return

    if argv and argv[0] == "--smoke-test":
        import tkinter as tk

        root = tk.Tk()
        root.title("clownfish-smoke-test")
        root.update_idletasks()
        root.destroy()
        print("GUI smoke test passed successfully")
        return

    if argv and argv[0] in ("-v", "--version"):
        print(f"clownfish {__version__}")
        return

    if argv and argv[0] in ("-h", "--help"):
        print(f"clownfish {__version__} - A modern terminal emulator written in Python and Tkinter")
        print("\nUsage:\n  clownfish [options] [command]")
        print("\nCommands:\n  ssh <destination>   Connect to a remote SSH host (e.g. clownfish ssh user@host -p 22)")
        print("\nOptions:")
        print("  -v, --version       Show version number and exit")
        print("  -h, --help          Show this help message and exit")
        print("  -c, --command CMD   Run command non-interactively in headless mode and exit")
        print("  --headless          Run in headless mode without GUI")
        print("  --restore           Restore saved session tabs and splits")
        print("  --no-restore        Start a fresh session, ignoring saved state")
        print("  --reconnect-ssh     Auto-reconnect SSH tabs on session restore (default)")
        print("  --no-reconnect-ssh  Do not auto-reconnect SSH tabs on restore")
        print("  --smoke-test        Test GUI window initialization and exit immediately")
        return

    command_to_run: str | None = None
    if "-c" in argv:
        c_idx = argv.index("-c")
        if c_idx + 1 < len(argv):
            command_to_run = argv[c_idx + 1]
            argv = argv[:c_idx] + argv[c_idx + 2:]
    elif "--command" in argv:
        c_idx = argv.index("--command")
        if c_idx + 1 < len(argv):
            command_to_run = argv[c_idx + 1]
            argv = argv[:c_idx] + argv[c_idx + 2:]

    from clownfish.config import TerminalConfig

    config = TerminalConfig.load()
    if "--no-restore" in argv:
        config.restore_session = False
    elif "--restore" in argv:
        config.restore_session = True

    if "--no-reconnect-ssh" in argv:
        config.auto_reconnect_ssh = False
    elif "--reconnect-ssh" in argv:
        config.auto_reconnect_ssh = True

    if command_to_run is not None:
        code = _run_headless_bridge(command=command_to_run, cols=config.cols, rows=config.rows)
        if code != 0:
            sys.exit(code)
        return

    if argv and argv[0] == "ssh":
        import argparse

        parser = argparse.ArgumentParser(prog="clownfish ssh", description="Connect to remote SSH host")
        parser.add_argument("destination", help="Remote host or user@host")
        parser.add_argument("-p", "--port", type=int, default=22, help="SSH port")
        parser.add_argument("-i", "--identity-file", help="Identity file path")
        parser.add_argument("--headless", action="store_true", help="Run in headless mode")
        args_parsed = parser.parse_args(argv[1:])

        dest = args_parsed.destination
        user = None
        host = dest
        if "@" in dest:
            user, host = dest.split("@", 1)

        from clownfish.transports.ssh import SSHTransport

        ssh_trans = SSHTransport(
            host=host,
            port=args_parsed.port,
            user=user,
            identity_file=args_parsed.identity_file,
            cols=config.cols,
            rows=config.rows,
        )

        if args_parsed.headless or "--headless" in argv:
            code = _run_headless_bridge(transport=ssh_trans, cols=config.cols, rows=config.rows)
            if code != 0:
                sys.exit(code)
            return

        import tkinter as tk

        from clownfish.frontends.tkinter.app import TkTerminalApp
        from clownfish.session.session import TerminalSession

        root = tk.Tk()
        root.title(f"clownfish - {dest}")
        dest_title = f"🌐 {dest}"
        session = TerminalSession(
            transport=ssh_trans,
            title=dest_title,
            cols=config.cols,
            rows=config.rows,
            max_scrollback=config.max_scrollback,
            auto_drain=False,
        )
        _ = TkTerminalApp(root, session=session, config=config)
        root.mainloop()
        return

    if argv and argv[0] == "--headless":
        code = _run_headless_bridge(cols=config.cols, rows=config.rows)
        if code != 0:
            sys.exit(code)
        return

    import tkinter as tk

    from clownfish.frontends.tkinter.app import TkTerminalApp

    root = tk.Tk()
    root.title("clownfish")

    icon_path = Path(__file__).resolve().parent / "clownfish.png"
    if icon_path.exists():
        try:
            app_icon = tk.PhotoImage(file=str(icon_path), master=root)
            root.iconphoto(True, app_icon)
        except (tk.TclError, OSError, RuntimeError):
            pass

    _ = TkTerminalApp(root, cols=80, rows=24, config=config)
    root.mainloop()
