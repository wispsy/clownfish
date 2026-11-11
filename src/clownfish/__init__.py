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
from clownfish.session.session import TerminalSession
from clownfish.session.transport import Transport
from clownfish.syntax import highlight_code, is_syntax_available, print_highlighted
from clownfish.transports.pty import PTYTransport
from clownfish.transports.ssh import SSHTransport

if TYPE_CHECKING:
    from clownfish.frontends.tkinter.app import TkTerminalApp

__version__ = "0.3.1"
__all__ = [
    "Cell",
    "PTYTransport",
    "PromptMarker",
    "SSHTransport",
    "ScreenBuffer",
    "Selection",
    "Style",
    "TerminalConfig",
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
]


def __getattr__(name: str) -> Any:
    if name == "TkTerminalApp":
        from clownfish.frontends.tkinter.app import TkTerminalApp

        return TkTerminalApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    """Launch clownfish terminal emulator."""
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
