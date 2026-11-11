"""Split pane management for dividing terminal views horizontally or vertically."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer


class SplitView(tk.Frame):
    """Container holding terminal panes with arbitrary horizontal and vertical splits."""

    def __init__(
        self,
        master: tk.Widget,
        config: TerminalConfig | None = None,
        on_pane_focus: Callable[[TerminalPane], None] | None = None,
        on_pane_close: Callable[[TerminalPane], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=TkCanvasRenderer.rgb_to_hex((config or TerminalConfig()).default_bg), **kwargs)
        self.config = config or TerminalConfig()
        self.on_pane_focus = on_pane_focus
        self.on_pane_close = on_pane_close

        self._panes: list[TerminalPane] = []
        self.active_pane: TerminalPane | None = None

        # Create initial primary pane
        initial_pane = self._create_pane(self)
        initial_pane.pack(fill=tk.BOTH, expand=True)
        self._panes.append(initial_pane)
        self.active_pane = initial_pane

    def _create_pane(self, parent: tk.Widget) -> TerminalPane:
        return TerminalPane(
            parent,
            config=self.config,
            on_focus=self._handle_pane_focus,
            on_close=self._handle_pane_close,
        )

    def _handle_pane_focus(self, pane: TerminalPane) -> None:
        self.active_pane = pane
        if self.on_pane_focus:
            self.on_pane_focus(pane)

    def _handle_pane_close(self, pane: TerminalPane) -> None:
        self.close_pane(pane)
        if self.on_pane_close:
            self.on_pane_close(pane)

    def panes(self) -> list[TerminalPane]:
        """Return all active terminal panes."""
        return list(self._panes)

    def split(self, target_pane: TerminalPane | None = None, orientation: str = "vertical") -> TerminalPane:
        """Split target pane (or active pane) in two along orientation ('horizontal' or 'vertical')."""
        target = target_pane or self.active_pane or (self._panes[0] if self._panes else None)
        if target is None:
            new_pane = self._create_pane(self)
            new_pane.pack(fill=tk.BOTH, expand=True)
            self._panes.append(new_pane)
            self.active_pane = new_pane
            return new_pane

        parent = target.master
        orient = tk.HORIZONTAL if orientation == "horizontal" else tk.VERTICAL

        # Create PanedWindow to replace target in parent
        paned = tk.PanedWindow(
            parent,
            orient=orient,
            sashwidth=4,
            sashrelief=tk.FLAT,
            bg="#2a2a32",
            bd=0,
        )

        # Retain packing info of target
        pack_info = target.pack_info() if hasattr(target, "pack_info") else {}
        target.pack_forget()

        if pack_info:
            paned.pack(**pack_info)
        else:
            paned.pack(fill=tk.BOTH, expand=True)

        # Reparent target pane into paned window
        # In Tkinter, reparenting widget master is done by recreating or re-packing
        # Instead, let's create paned window and add target and new_pane to paned
        paned.add(target, stretch="always")
        new_pane = self._create_pane(paned)
        paned.add(new_pane, stretch="always")

        self._panes.append(new_pane)
        self.active_pane = new_pane
        new_pane.focus()
        return new_pane

    def split_horizontal(self, target_pane: TerminalPane | None = None) -> TerminalPane:
        """Split side-by-side."""
        return self.split(target_pane, orientation="horizontal")

    def split_vertical(self, target_pane: TerminalPane | None = None) -> TerminalPane:
        """Split top-and-bottom."""
        return self.split(target_pane, orientation="vertical")

    def close_pane(self, pane: TerminalPane) -> None:
        """Close and remove a pane from the split view."""
        if pane not in self._panes:
            return

        self._panes.remove(pane)
        parent = pane.master

        if isinstance(parent, tk.PanedWindow):
            # Check remaining siblings
            remaining = [w for w in parent.panes() if w != str(pane)]
            pane.close()
            if len(remaining) == 1:
                # Collapse PanedWindow into parent
                remaining_widget = self.nametowidget(remaining[0])
                pack_info = parent.pack_info()
                parent.pack_forget()
                parent.remove(remaining_widget)
                if pack_info:
                    remaining_widget.pack(**pack_info)
                else:
                    remaining_widget.pack(fill=tk.BOTH, expand=True)
                parent.destroy()
        else:
            pane.close()

        # Update active pane
        if self.active_pane == pane:
            self.active_pane = self._panes[-1] if self._panes else None
            if self.active_pane:
                self.active_pane.focus()
