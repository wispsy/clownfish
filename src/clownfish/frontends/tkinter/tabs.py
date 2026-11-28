"""Multi-tab manager and tab-bar component for desktop terminal windows."""

from __future__ import annotations

import os
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.split import SplitView

if TYPE_CHECKING:
    from clownfish.session.session import TerminalSession


class TabbedTerminalView(tk.Frame):
    """Container managing multiple terminal tabs with a custom tab bar."""

    def __init__(
        self,
        master: tk.Widget,
        config: TerminalConfig | None = None,
        on_title_changed: Callable[[str], None] | None = None,
        on_all_closed: Callable[[], None] | None = None,
        initial_session: TerminalSession | None = None,
        initial_title: str | None = None,
        auto_create_tab: bool = True,
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

        # Create first tab if requested
        if auto_create_tab:
            self.new_tab(title=initial_title, initial_session=initial_session)

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

    def new_tab(
        self,
        title: str | None = None,
        cwd: str | None = None,
        initial_session: TerminalSession | None = None,
    ) -> SplitView:
        """Create and switch to a new tab, inheriting CWD from active pane if available."""
        tab_idx = len(self.tabs) + 1
        tab_title = title or f"Terminal {tab_idx}"
        target_cwd = cwd
        if (
            target_cwd is None
            and self.active_pane
            and getattr(self.active_pane, "session", None)
            and self.active_pane.session.cwd
        ):
            target_cwd = self.active_pane.session.cwd
        if target_cwd and not os.path.isdir(target_cwd):
            target_cwd = str(Path.home())

        split_view = SplitView(
            self.content_frame,
            config=self.config,
            on_pane_focus=self._on_pane_focused,
            on_pane_close=self._on_pane_closed,
            on_pane_title=self._on_pane_title_changed,
            cwd=target_cwd,
            initial_session=initial_session,
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

    def apply_config(self, config: TerminalConfig) -> None:
        """Propagate updated configuration and theme to all tabs and split views."""
        self.config = config
        try:
            self.tab_bar.configure(bg=config.tab_bar_bg)
            self._tabs_container.configure(bg=config.tab_bar_bg)
            self._add_btn.configure(
                bg=config.tab_bar_bg,
                fg=config.tab_fg,
                activebackground=config.tab_active_bg,
                activeforeground=config.tab_active_fg,
            )
            self.content_frame.configure(bg=config.tab_active_bg)
        except tk.TclError, AttributeError:
            pass

        for _, sv in self.tabs:
            sv.apply_config(config)

        self._render_tab_bar()

    def close_tab(self, index: int | None = None) -> None:
        """Close tab at index (defaulting to current active tab)."""
        if not self.tabs:
            return

        target_idx = self.active_tab_index if index is None else index
        if not (0 <= target_idx < len(self.tabs)):
            return

        active_sv = self.active_split_view

        _, sv = self.tabs.pop(target_idx)
        for pane in sv.panes():
            pane.close()
        sv.destroy()

        if not self.tabs:
            if self.on_all_closed:
                self.on_all_closed()
            return

        # If a background tab closed, keep the active tab focused
        if sv is not active_sv:
            new_idx = next((i for i, (_, s) in enumerate(self.tabs) if s is active_sv), 0)
        else:
            new_idx = min(target_idx, len(self.tabs) - 1)

        self.switch_tab(new_idx)

    def request_close_tab(self, index: int) -> bool:
        """Close tab at index, asking for confirmation if running processes are active."""
        if not (0 <= index < len(self.tabs)):
            return False

        if getattr(self.config, "confirm_close_active_process", True):
            sv = self.tabs[index][1]
            has_running = any(pane.has_foreground_process() for pane in sv.panes())
            if has_running:
                from tkinter import messagebox

                tab_title = self.tabs[index][0]
                try:
                    confirmed = messagebox.askyesno(
                        "Close Tab?",
                        f"A process is currently running in tab '{tab_title}'.\n"
                        "Closing it will terminate the process. Close anyway?",
                        parent=self.winfo_toplevel(),
                    )
                    if not confirmed:
                        return False
                except tk.TclError, OSError, RuntimeError:
                    return False

        self.close_tab(index)
        return True

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

    def new_ssh_tab(
        self,
        host: str,
        user: str | None = None,
        port: int = 22,
        identity_file: str | None = None,
        extra_args: list[str] | None = None,
        title: str | None = None,
    ) -> SplitView:
        """Create and switch to a new tab connected to a remote host via SSH."""
        from clownfish.session.session import TerminalSession
        from clownfish.transports.ssh import SSHTransport

        ssh_trans = SSHTransport(
            host=host,
            port=port,
            user=user,
            identity_file=identity_file,
            extra_args=extra_args,
            cols=self.config.cols,
            rows=self.config.rows,
        )
        dest_str = f"{user}@{host}" if user else host
        tab_title = title or f"🌐 {dest_str}"

        session = TerminalSession(
            cols=self.config.cols,
            rows=self.config.rows,
            max_scrollback=self.config.max_scrollback,
            transport=ssh_trans,
            title=tab_title,
            auto_drain=False,
        )

        return self.new_tab(title=tab_title, initial_session=session)

    def dump_state(self):
        """Serialize all tabs and split layouts to a SessionState."""
        from clownfish.session.persistence import SessionState, TabState

        tabs_state = []
        for title, sv in self.tabs:
            tab_state = TabState(title=title, root=sv.dump_state())
            tabs_state.append(tab_state)

        return SessionState(
            version=1,
            active_tab_index=self.active_tab_index,
            tabs=tabs_state,
        )

    def load_state(self, state) -> bool:
        """Restore tabs and split layouts from a SessionState."""
        if not getattr(state, "tabs", None):
            return False

        while self.tabs:
            _, sv = self.tabs.pop()
            for p in sv.panes():
                p.close()
            sv.destroy()

        for tab_state in state.tabs:
            sv = SplitView(
                self.content_frame,
                config=self.config,
                on_pane_focus=self._on_pane_focused,
                on_pane_close=self._on_pane_closed,
                on_pane_title=self._on_pane_title_changed,
                create_initial_pane=False,
            )
            sv.load_state(tab_state.root)
            self.tabs.append((tab_state.title, sv))

        target_idx = max(0, min(len(self.tabs) - 1, state.active_tab_index))
        self.switch_tab(target_idx)
        return True

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
            close_lbl.bind("<Button-1>", lambda e, i=idx: self.request_close_tab(i))

    def _on_pane_focused(self, pane: TerminalPane) -> None:
        pass

    def _on_pane_title_changed(self, pane: TerminalPane, title: str) -> None:
        for idx, (_, sv) in enumerate(self.tabs):
            if pane in sv.panes():
                self.set_tab_title(idx, title)
                break

    def _on_pane_closed(self, pane: TerminalPane) -> None:
        """Clean up tabs when panes close, correctly handling background tab disconnects."""
        for idx in range(len(self.tabs) - 1, -1, -1):
            _, sv = self.tabs[idx]
            if not sv.panes():
                self.close_tab(idx)
