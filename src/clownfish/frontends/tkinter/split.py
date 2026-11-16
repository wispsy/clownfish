"""Split pane management for dividing terminal views horizontally or vertically."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer


class SplitView(tk.Frame):
    """Container holding terminal panes with arbitrary nested horizontal and vertical splits."""

    def __init__(
        self,
        master: tk.Widget,
        config: TerminalConfig | None = None,
        on_pane_focus: Callable[[TerminalPane], None] | None = None,
        on_pane_close: Callable[[TerminalPane], None] | None = None,
        on_pane_title: Callable[[TerminalPane, str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=TkCanvasRenderer.rgb_to_hex((config or TerminalConfig()).default_bg), **kwargs)
        self.config = config or TerminalConfig()
        self.on_pane_focus = on_pane_focus
        self.on_pane_close = on_pane_close
        self.on_pane_title = on_pane_title

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
            on_title_change=self._handle_pane_title,
        )

    def _handle_pane_focus(self, pane: TerminalPane) -> None:
        self.active_pane = pane
        if self.on_pane_focus:
            self.on_pane_focus(pane)

    def _handle_pane_close(self, pane: TerminalPane) -> None:
        self.close_pane(pane)
        if self.on_pane_close:
            self.on_pane_close(pane)

    def _handle_pane_title(self, pane: TerminalPane, title: str) -> None:
        if self.on_pane_title:
            self.on_pane_title(pane, title)

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

        orient = tk.HORIZONTAL if orientation == "horizontal" else tk.VERTICAL
        parent = target.master

        if parent == self:
            # First split from the root SplitView frame
            paned = tk.PanedWindow(
                self,
                orient=orient,
                sashwidth=4,
                sashrelief=tk.FLAT,
                bg="#2a2a32",
                bd=0,
            )
            target.pack_forget()
            paned.pack(fill=tk.BOTH, expand=True)

            paned.add(target, stretch="always")
            new_pane = self._create_pane(paned)
            paned.add(new_pane, stretch="always")

            self._panes.append(new_pane)
            self.active_pane = new_pane
            new_pane.focus()
            return new_pane

        if isinstance(parent, tk.PanedWindow):
            current_orient = parent.cget("orient")
            if str(current_orient) == str(orient):
                # Sibling split in existing PanedWindow
                new_pane = self._create_pane(parent)
                parent.add(new_pane, after=str(target), stretch="always")
                self._panes.append(new_pane)
                self.active_pane = new_pane
                new_pane.focus()
                return new_pane

            # Nested split requiring a perpendicular PanedWindow
            nested_paned = tk.PanedWindow(
                parent,
                orient=orient,
                sashwidth=4,
                sashrelief=tk.FLAT,
                bg="#2a2a32",
                bd=0,
            )
            parent.add(nested_paned, after=str(target), stretch="always")
            parent.forget(target)

            nested_paned.add(target, stretch="always")
            new_pane = self._create_pane(nested_paned)
            nested_paned.add(new_pane, stretch="always")

            self._panes.append(new_pane)
            self.active_pane = new_pane
            new_pane.focus()
            return new_pane

        # Fallback
        new_pane = self._create_pane(self)
        new_pane.pack(fill=tk.BOTH, expand=True)
        self._panes.append(new_pane)
        self.active_pane = new_pane
        return new_pane

    def split_horizontal(self, target_pane: TerminalPane | None = None) -> TerminalPane:
        """Split side-by-side."""
        return self.split(target_pane, orientation="horizontal")

    def split_vertical(self, target_pane: TerminalPane | None = None) -> TerminalPane:
        """Split top-and-bottom."""
        return self.split(target_pane, orientation="vertical")

    def close_pane(self, pane: TerminalPane) -> None:
        """Close and remove a pane from the split view hierarchy."""
        if pane not in self._panes:
            return

        self._panes.remove(pane)
        parent = pane.master

        if isinstance(parent, tk.PanedWindow):
            remaining = [w for w in parent.panes() if w != str(pane)]
            try:
                parent.forget(pane)
            except tk.TclError:
                pass
            pane.close()

            if len(remaining) == 1:
                # Collapse single-child PanedWindow into parent
                remaining_widget = self.nametowidget(remaining[0])
                grandparent = parent.master
                if grandparent == self:
                    try:
                        parent.forget(remaining_widget)
                    except tk.TclError:
                        pass
                    parent.destroy()
                    remaining_widget.pack(fill=tk.BOTH, expand=True)
                elif isinstance(grandparent, tk.PanedWindow):
                    try:
                        grandparent.add(remaining_widget, after=str(parent), stretch="always")
                        grandparent.forget(parent)
                    except tk.TclError:
                        pass
                    parent.destroy()
            elif len(remaining) == 0:
                parent.destroy()
        else:
            pane.close()

        # Update active pane
        if self.active_pane == pane or self.active_pane not in self._panes:
            self.active_pane = self._panes[-1] if self._panes else None
            if self.active_pane:
                self.active_pane.focus()
