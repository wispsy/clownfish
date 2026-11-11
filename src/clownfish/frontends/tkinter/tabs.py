"""Multi-tab manager and tab-bar component for desktop terminal windows."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.split import SplitView


class TabbedTerminalView(tk.Frame):
    """Container managing multiple terminal tabs with a custom tab bar."""

    def __init__(
        self,
        master: tk.Widget,
        config: TerminalConfig | None = None,
        on_title_changed: Callable[[str], None] | None = None,
        on_all_closed: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        self.config = config or TerminalConfig()
        super().__init__(master, bg=self.config.tab_bar_bg, **kwargs)

        self.on_title_changed = on_title_changed
        self.on_all_closed = on_all_closed

        self.tabs: list[tuple[str, SplitView]] = []
        self.active_tab_index = 0

        # Tab Bar Header
        self.tab_bar = tk.Frame(self, bg=self.config.tab_bar_bg, height=28)
        self.tab_bar.pack(side=tk.TOP, fill=tk.X)
        self.tab_bar.pack_propagate(False)

        # Tab buttons container
        self._tabs_container = tk.Frame(self.tab_bar, bg=self.config.tab_bar_bg)
        self._tabs_container.pack(side=tk.LEFT, fill=tk.Y)

        # Add Tab button
        self._add_btn = tk.Button(
            self.tab_bar,
            text="+",
            command=self.new_tab,
            relief=tk.FLAT,
            bg=self.config.tab_bar_bg,
            fg=self.config.tab_fg,
            activebackground=self.config.tab_active_bg,
            activeforeground=self.config.tab_active_fg,
            padx=8,
            bd=0,
            font=("Helvetica", 12, "bold"),
        )
        self._add_btn.pack(side=tk.LEFT, fill=tk.Y, padx=2)

        # Body Frame for active SplitView
        self.content_frame = tk.Frame(self, bg=self.config.tab_active_bg)
        self.content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # Create first tab
        self.new_tab()

    @property
    def active_split_view(self) -> SplitView | None:
        """Return active tab's SplitView."""
        if 0 <= self.active_tab_index < len(self.tabs):
            return self.tabs[self.active_tab_index][1]
        return None

    @property
    def active_pane(self) -> TerminalPane | None:
        """Return currently active terminal pane across all tabs."""
        sv = self.active_split_view
        return sv.active_pane if sv else None

    def new_tab(self, title: str | None = None) -> SplitView:
        """Create and switch to a new tab."""
        tab_idx = len(self.tabs) + 1
        tab_title = title or f"Terminal {tab_idx}"

        split_view = SplitView(
            self.content_frame,
            config=self.config,
            on_pane_focus=self._on_pane_focused,
            on_pane_close=self._on_pane_closed,
        )

        self.tabs.append((tab_title, split_view))
        self.switch_tab(len(self.tabs) - 1)
        return split_view

    def switch_tab(self, index: int) -> None:
        """Switch active tab to given index."""
        if not self.tabs:
            return

        index = max(0, min(len(self.tabs) - 1, index))
        self.active_tab_index = index

        # Hide all split views and pack active one
        for i, (_, sv) in enumerate(self.tabs):
            if i == index:
                sv.pack(fill=tk.BOTH, expand=True)
            else:
                sv.pack_forget()

        self._render_tab_bar()

        active_pane = self.active_pane
        if active_pane:
            active_pane.focus()
            if self.on_title_changed:
                self.on_title_changed(self.tabs[index][0])

    def close_tab(self, index: int | None = None) -> None:
        """Close tab at index (defaulting to current active tab)."""
        if not self.tabs:
            return

        target_idx = self.active_tab_index if index is None else index
        if not (0 <= target_idx < len(self.tabs)):
            return

        _, sv = self.tabs.pop(target_idx)
        for pane in sv.panes():
            pane.close()
        sv.destroy()

        if not self.tabs:
            if self.on_all_closed:
                self.on_all_closed()
            return

        # Adjust active index
        new_idx = min(target_idx, len(self.tabs) - 1)
        self.switch_tab(new_idx)

    def next_tab(self) -> None:
        """Switch to next tab cycling forward."""
        if self.tabs:
            self.switch_tab((self.active_tab_index + 1) % len(self.tabs))

    def prev_tab(self) -> None:
        """Switch to previous tab cycling backward."""
        if self.tabs:
            self.switch_tab((self.active_tab_index - 1) % len(self.tabs))

    def set_tab_title(self, index: int, title: str) -> None:
        """Update display title for tab at index."""
        if 0 <= index < len(self.tabs):
            sv = self.tabs[index][1]
            self.tabs[index] = (title, sv)
            self._render_tab_bar()
            if index == self.active_tab_index and self.on_title_changed:
                self.on_title_changed(title)

    def _render_tab_bar(self) -> None:
        """Redraw tab header buttons in tab bar."""
        for widget in self._tabs_container.winfo_children():
            widget.destroy()

        for idx, (title, _) in enumerate(self.tabs):
            is_active = idx == self.active_tab_index
            bg_color = self.config.tab_active_bg if is_active else self.config.tab_bar_bg
            fg_color = self.config.tab_active_fg if is_active else self.config.tab_fg

            tab_frame = tk.Frame(self._tabs_container, bg=bg_color, padx=8, pady=2)
            tab_frame.pack(side=tk.LEFT, fill=tk.Y, padx=1)

            btn = tk.Label(
                tab_frame,
                text=title,
                bg=bg_color,
                fg=fg_color,
                font=("Helvetica", 11, "bold" if is_active else "normal"),
                cursor="arrow",
            )
            btn.pack(side=tk.LEFT, padx=(0, 4))
            btn.bind("<Button-1>", lambda e, i=idx: self.switch_tab(i))
            tab_frame.bind("<Button-1>", lambda e, i=idx: self.switch_tab(i))

            # Close 'x' button
            close_lbl = tk.Label(
                tab_frame,
                text="✕",
                bg=bg_color,
                fg=fg_color,
                font=("Helvetica", 9),
                cursor="arrow",
            )
            close_lbl.pack(side=tk.LEFT)
            close_lbl.bind("<Button-1>", lambda e, i=idx: self.close_tab(i))

    def _on_pane_focused(self, pane: TerminalPane) -> None:
        pass

    def _on_pane_closed(self, pane: TerminalPane) -> None:
        sv = self.active_split_view
        if sv and not sv.panes():
            self.close_tab(self.active_tab_index)
