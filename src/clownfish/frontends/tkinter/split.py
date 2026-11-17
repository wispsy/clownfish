"""Split pane management for dividing terminal views horizontally or vertically."""

from __future__ import annotations

import os
import tkinter as tk
from collections.abc import Callable
from pathlib import Path

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
        cwd: str | None = None,
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
        initial_cwd = cwd
        if initial_cwd and not os.path.isdir(initial_cwd):
            initial_cwd = str(Path.home())
        initial_pane = self._create_pane(self, cwd=initial_cwd)
        initial_pane.pack(fill=tk.BOTH, expand=True)
        self._panes.append(initial_pane)
        self.active_pane = initial_pane

    def _create_pane(self, parent: tk.Widget, cwd: str | None = None) -> TerminalPane:
        return TerminalPane(
            parent,
            config=self.config,
            on_focus=self._handle_pane_focus,
            on_close=self._handle_pane_close,
            on_title_change=self._handle_pane_title,
            cwd=cwd,
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
        target_cwd = (
            target.session.cwd
            if target and getattr(target, "session", None) and target.session.cwd
            else (self.active_pane.session.cwd if self.active_pane and getattr(self.active_pane, "session", None) else None)
        )
        if target_cwd and not os.path.isdir(target_cwd):
            target_cwd = str(Path.home())
        if target is None:
            new_pane = self._create_pane(self, cwd=target_cwd)
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
            new_pane = self._create_pane(paned, cwd=target_cwd)
            paned.add(new_pane, stretch="always")

            self._panes.append(new_pane)
            self.active_pane = new_pane
            new_pane.focus()
            return new_pane

        if isinstance(parent, tk.PanedWindow):
            current_orient = parent.cget("orient")
            if str(current_orient) == str(orient):
                # Sibling split in existing PanedWindow
                new_pane = self._create_pane(parent, cwd=target_cwd)
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
            new_pane = self._create_pane(nested_paned, cwd=target_cwd)
            nested_paned.add(new_pane, stretch="always")

            self._panes.append(new_pane)
            self.active_pane = new_pane
            new_pane.focus()
            return new_pane

        # Fallback
        new_pane = self._create_pane(self, cwd=target_cwd)
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

    def focus_next_pane(self) -> TerminalPane | None:
        """Cycle focus to next split pane."""
        if not self._panes:
            return None
        try:
            curr_idx = self._panes.index(self.active_pane) if self.active_pane else 0
        except ValueError:
            curr_idx = 0
        next_idx = (curr_idx + 1) % len(self._panes)
        pane = self._panes[next_idx]
        pane.focus()
        return pane

    def focus_prev_pane(self) -> TerminalPane | None:
        """Cycle focus to previous split pane."""
        if not self._panes:
            return None
        try:
            curr_idx = self._panes.index(self.active_pane) if self.active_pane else 0
        except ValueError:
            curr_idx = 0
        prev_idx = (curr_idx - 1) % len(self._panes)
        pane = self._panes[prev_idx]
        pane.focus()
        return pane

    def equalize_splits(self) -> None:
        """Reset sash positions across PanedWindows to equal proportions."""
        for widget in self.winfo_children():
            self._equalize_widget(widget)

    def _equalize_widget(self, widget: tk.Widget) -> None:
        if isinstance(widget, tk.PanedWindow):
            panes = widget.panes()
            if len(panes) > 1:
                widget.update_idletasks()
                is_horiz = str(widget.cget("orient")) == str(tk.HORIZONTAL)
                total_dim = widget.winfo_width() if is_horiz else widget.winfo_height()
                step = total_dim // len(panes)
                for i in range(len(panes) - 1):
                    coord = (i + 1) * step
                    try:
                        if is_horiz:
                            widget.sash_place(i, coord, 0)
                        else:
                            widget.sash_place(i, 0, coord)
                    except tk.TclError:
                        pass
            for p in widget.panes():
                try:
                    child = self.nametowidget(p)
                    self._equalize_widget(child)
                except (KeyError, tk.TclError):
                    pass
