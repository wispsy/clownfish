"""Tkinter desktop frontend components for clownfish."""

from clownfish.frontends.tkinter.app import TkTerminalApp
from clownfish.frontends.tkinter.input import TkInputHandler
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer
from clownfish.frontends.tkinter.split import SplitView
from clownfish.frontends.tkinter.tabs import TabbedTerminalView

__all__ = [
    "SplitView",
    "TabbedTerminalView",
    "TerminalPane",
    "TkCanvasRenderer",
    "TkInputHandler",
    "TkTerminalApp",
]
