"""clownfish - A modern terminal emulator written in Python and Tkinter."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from clownfish.models import Cell, Selection, Style
from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer

if TYPE_CHECKING:
    from clownfish.app import TkTerminalApp

__version__ = "0.2.0"
__all__ = [
    "Cell",
    "ScreenBuffer",
    "Selection",
    "Style",
    "TkTerminalApp",
    "VT100Parser",
    "main",
]


def __getattr__(name: str) -> Any:
    if name == "TkTerminalApp":
        from clownfish.app import TkTerminalApp

        return TkTerminalApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    """Launch clownfish terminal emulator."""
    import tkinter as tk

    from clownfish.app import TkTerminalApp

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
