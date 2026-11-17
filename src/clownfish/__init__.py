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
    from clownfish.frontends.tkinter.app import TkTerminalApp
    from clownfish.frontends.tkinter.pane import TerminalPane
    from clownfish.frontends.tkinter.split import SplitView
    from clownfish.frontends.tkinter.tabs import TabbedTerminalView
    from clownfish.transports.pty import PTYTransport
    from clownfish.transports.ssh import SSHTransport

__version__ = "0.4.9"
__all__ = [
    "Cell",
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

    import tkinter as tk

    from clownfish.frontends.tkinter.app import TkTerminalApp

    root = tk.Tk()
    root.title("clownfish")

    icon_path = Path(__file__).resolve().parent / "clownfish.png"
    if icon_path.exists():
        try:
            app_icon = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, app_icon)
        except (tk.TclError, OSError):
            pass

    _ = TkTerminalApp(root, cols=80, rows=24)
    root.mainloop()
