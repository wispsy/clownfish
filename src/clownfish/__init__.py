"""clownfish - A modern terminal emulator written in Python and Tkinter."""

import tkinter as tk
from pathlib import Path

from clownfish.app import TkTerminalApp
from clownfish.models import Cell, Selection, Style
from clownfish.parser import VT100Parser
from clownfish.screen import ScreenBuffer

__version__ = "0.1.0"
__all__ = [
    "Cell",
    "ScreenBuffer",
    "Selection",
    "Style",
    "TkTerminalApp",
    "VT100Parser",
    "main",
]


def main() -> None:
    """Launch clownfish terminal emulator."""
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
