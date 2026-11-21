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

__version__ = "0.6.0"
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
        print("  --headless          Run in headless mode without GUI")
        print("  --restore           Restore saved session tabs and splits")
        print("  --no-restore        Start a fresh session, ignoring saved state")
        return

    from clownfish.config import TerminalConfig

    config = TerminalConfig.load()
    if "--no-restore" in argv:
        config.restore_session = False
    elif "--restore" in argv:
        config.restore_session = True

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
            from clownfish.frontends.headless import HeadlessTerminal

            with HeadlessTerminal(transport=ssh_trans) as term:
                import time

                while term.is_alive():
                    term.drain()
                    time.sleep(0.05)
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
        from clownfish.frontends.headless import HeadlessTerminal

        with HeadlessTerminal(cols=config.cols, rows=config.rows) as term:
            import time

            while term.is_alive():
                term.drain()
                time.sleep(0.05)
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
