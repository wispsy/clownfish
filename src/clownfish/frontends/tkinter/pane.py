"""Modular terminal pane widget embedding session, canvas renderer, and search overlay."""

from __future__ import annotations

import sys
import tkinter as tk
from collections.abc import Callable

from clownfish.config import TerminalConfig
from clownfish.core.search import SearchMatch, SearchState, search_screen
from clownfish.frontends.tkinter.input import TkInputHandler
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer
from clownfish.session.session import TerminalSession


class TerminalPane(tk.Frame):
    """Reusable terminal pane embedding a TerminalSession, canvas renderer, and search bar."""

    def __init__(
        self,
        master: tk.Widget,
        session: TerminalSession | None = None,
        cols: int = 80,
        rows: int = 24,
        config: TerminalConfig | None = None,
        on_focus: Callable[[TerminalPane], None] | None = None,
        on_close: Callable[[TerminalPane], None] | None = None,
        on_title_change: Callable[[TerminalPane, str], None] | None = None,
        cwd: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=TkCanvasRenderer.rgb_to_hex((config or TerminalConfig()).default_bg), **kwargs)
        self.config = config or TerminalConfig(cols=cols, rows=rows)
        self.cols = cols
        self.rows = rows
        self.on_focus = on_focus
        self.on_close = on_close
        self.on_title_change = on_title_change

        self.session = session or TerminalSession(
            cols=cols,
            rows=rows,
            max_scrollback=self.config.max_scrollback,
            on_title_changed=self._on_title_changed,
            on_close=self._on_session_close,
            auto_drain=False,
            cwd=cwd,
        )
        self.session.auto_drain = False
        self.session.on_title_changed = self._on_title_changed
        self.session.on_close = self._on_session_close
        self.session.on_bell = self._on_bell
        self.session.on_clipboard_write = self._on_clipboard_write
        self.session.on_clipboard_query = self._on_clipboard_query
        self.session.on_notification = self._on_notification
        self.session.set_event_notifier(self._on_session_event)

        self.screen = self.session.screen
        self.parser = self.session.parser
        self.search_state = SearchState()

        # Canvas
        self.canvas = tk.Canvas(
            self,
            width=self.cols * 8,
            height=self.rows * 16,
            bg=TkCanvasRenderer.rgb_to_hex(self.config.default_bg),
            highlightthickness=1,
            highlightbackground="#2a2a32",
            highlightcolor="#4a90e2",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.renderer = TkCanvasRenderer(self.canvas, self.config)
        self.cell_w = self.renderer.cell_w
        self.cell_h = self.renderer.cell_h
        self.canvas.config(width=self.cols * self.cell_w, height=self.rows * self.cell_h)

        self.input_handler = TkInputHandler(self.session)

        # Search Bar Overlay (hidden by default)
        self._search_frame: tk.Frame | None = None
        self._search_entry: tk.Entry | None = None
        self._search_label: tk.Label | None = None
        self._init_search_bar()

        self._bind_events()
        self.session.start()
        self._tick_job: str | None = None
        self._render_tick()

    @property
    def selection(self):
        """Return the active text selection from the input handler."""
        return self.input_handler.selection

    @selection.setter
    def selection(self, val):
        self.input_handler.selection = val

    def _init_search_bar(self) -> None:
        self._search_frame = tk.Frame(self, bg="#202025", padx=6, pady=4)
        lbl = tk.Label(self._search_frame, text="Find:", fg="#cccccc", bg="#202025", font=("Helvetica", 11))
        lbl.pack(side=tk.LEFT, padx=(0, 4))

        self._search_entry = tk.Entry(
            self._search_frame, bg="#2d2d35", fg="#ffffff", insertbackground="#ffffff", width=20, font=("Helvetica", 11)
        )
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self._search_entry.bind("<KeyRelease>", self._on_search_text_changed)
        self._search_entry.bind("<Return>", lambda e: self.search_next())
        self._search_entry.bind("<Shift-Return>", lambda e: self.search_prev())
        self._search_entry.bind("<Escape>", lambda e: self.close_search())

        self._search_label = tk.Label(
            self._search_frame, text="0 of 0", fg="#888888", bg="#202025", font=("Helvetica", 10)
        )
        self._search_label.pack(side=tk.LEFT, padx=4)

        prev_btn = tk.Button(
            self._search_frame, text="▲", command=self.search_prev, relief=tk.FLAT, bg="#2d2d35", fg="#ffffff", padx=4
        )
        prev_btn.pack(side=tk.LEFT, padx=1)

        next_btn = tk.Button(
            self._search_frame, text="▼", command=self.search_next, relief=tk.FLAT, bg="#2d2d35", fg="#ffffff", padx=4
        )
        next_btn.pack(side=tk.LEFT, padx=1)

        close_btn = tk.Button(
            self._search_frame, text="✕", command=self.close_search, relief=tk.FLAT, bg="#202025", fg="#aaaaaa", padx=4
        )
        close_btn.pack(side=tk.LEFT, padx=(4, 0))

    def _bind_events(self) -> None:
        # Focus
        self.canvas.bind("<FocusIn>", self._on_focus_in)
        self.canvas.bind("<FocusOut>", self._on_focus_out)

        # Mouse & Pointer Interactions
        self.canvas.bind("<Button-1>", self._on_button_1_press)
        self.canvas.bind("<B1-Motion>", self._on_button_1_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_1_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Triple-Button-1>", self._on_triple_click)
        self.canvas.bind("<Motion>", self._on_pointer_motion)

        # Mouse Wheel
        self.canvas.bind("<Button-4>", lambda e: self._on_mouse_scroll(-3, e))
        self.canvas.bind("<Button-5>", lambda e: self._on_mouse_scroll(3, e))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Key press
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.bind("<Configure>", self._on_configure)

    def _on_focus_in(self, event: tk.Event | None = None) -> None:
        try:
            self.canvas.config(highlightbackground="#4a90e2", highlightcolor="#4a90e2")
        except tk.TclError:
            pass
        if getattr(self.session.parser, "focus_reporting", False):
            self.session.write(b"\x1b[I")
        if self.on_focus:
            self.on_focus(self)

    def _on_focus_out(self, event: tk.Event | None = None) -> None:
        try:
            self.canvas.config(highlightbackground="#2a2a32", highlightcolor="#2a2a32")
        except tk.TclError:
            pass
        if getattr(self.session.parser, "focus_reporting", False):
            self.session.write(b"\x1b[O")

    def focus(self) -> None:
        """Focus the terminal canvas."""
        self.canvas.focus_set()
        if self.on_focus:
            self.on_focus(self)

    # --- Mouse Events ---

    def _on_button_1_press(self, event: tk.Event) -> None:
        self.focus()
        self.input_handler.on_button_1_press(event, self.cell_w, self.cell_h, self.canvas)
        self.renderer.draw_selection(self.input_handler.selection, self.cols)

    def _on_button_1_motion(self, event: tk.Event) -> None:
        self.input_handler.on_button_1_motion(event, self.cell_w, self.cell_h)
        self.renderer.draw_selection(self.input_handler.selection, self.cols)

    def _on_button_1_release(self, event: tk.Event) -> None:
        self.input_handler.on_button_1_release(event, self.cell_w, self.cell_h, self.canvas)

    def _on_double_click(self, event: tk.Event) -> None:
        self.input_handler.on_double_click(event, self.cell_w, self.cell_h)
        self.renderer.draw_selection(self.input_handler.selection, self.cols)

    def _on_triple_click(self, event: tk.Event) -> None:
        self.input_handler.on_triple_click(event, self.cell_w, self.cell_h)
        self.renderer.draw_selection(self.input_handler.selection, self.cols)

    def _on_pointer_motion(self, event: tk.Event) -> None:
        self.input_handler.on_pointer_motion(event, self.cell_w, self.cell_h, self.canvas)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = -event.delta if sys.platform == "darwin" else (-1 if event.delta > 0 else 1) * 3
        self._on_mouse_scroll(delta, event)

    def _on_mouse_scroll(self, delta: int, event: tk.Event | None = None) -> None:
        self.input_handler.on_mouse_scroll(delta, event, self.cell_w, self.cell_h, self.canvas)
        if self.search_state.matches:
            self.renderer.draw_search_matches(
                self.search_state.matches, self.search_state.current_match, self.screen, self.cols, self.rows
            )

    def _on_key_press(self, event: tk.Event) -> str:
        return self.input_handler.on_key_press(event, self.canvas)

    # --- Search Functionality ---

    def toggle_search(self) -> None:
        """Toggle visibility of the search bar."""
        if self._search_frame and self._search_frame.winfo_viewable():
            self.close_search()
        else:
            self.open_search()

    def open_search(self) -> None:
        """Show search bar and focus input."""
        if self._search_frame:
            self._search_frame.pack(side=tk.TOP, fill=tk.X, before=self.canvas)
            if self._search_entry:
                self._search_entry.focus_set()
                self._search_entry.select_range(0, tk.END)

    def close_search(self) -> None:
        """Hide search bar, clear search highlights, and return focus to canvas."""
        if self._search_frame:
            self._search_frame.pack_forget()
        self.search_state.clear()
        self.canvas.delete("search_highlight")
        self.canvas.focus_set()

    def _on_search_text_changed(self, event: tk.Event | None = None) -> None:
        query = self._search_entry.get() if self._search_entry else ""
        if not query:
            self.search_state.clear()
            self.canvas.delete("search_highlight")
            if self._search_label:
                self._search_label.config(text="0 of 0")
            return

        matches = search_screen(self.screen, query)
        self.search_state.set_results(query, matches)
        self._update_search_ui()

    def search_next(self) -> None:
        """Select next search match."""
        self.search_state.next_match()
        self._update_search_ui(jump=True)

    def search_prev(self) -> None:
        """Select previous search match."""
        self.search_state.prev_match()
        self._update_search_ui(jump=True)

    def _update_search_ui(self, jump: bool = True) -> None:
        total = self.search_state.total
        cur = self.search_state.current_index + 1 if total > 0 else 0
        if self._search_label:
            self._search_label.config(text=f"{cur} of {total}")

        active_match = self.search_state.current_match
        if jump and active_match is not None:
            self._jump_to_match(active_match)

        self.renderer.draw_search_matches(
            self.search_state.matches, active_match, self.screen, self.cols, self.rows
        )

    def _jump_to_match(self, match: SearchMatch) -> None:
        """Scroll buffer to ensure the search match is visible."""
        sb_len = len(self.screen.scrollback)
        top_visible = sb_len - self.screen.scroll_offset

        # Check if match is outside currently visible viewport
        if match.absolute_row < top_visible or match.absolute_row >= top_visible + self.rows:
            # Position match near vertical center
            target_offset = sb_len - match.absolute_row + (self.rows // 2)
            self.screen.scroll_offset = max(0, min(sb_len, target_offset))
            self.screen.mark_all_dirty()

    # --- Resize & Session Events ---

    def _on_configure(self, event: tk.Event) -> None:
        new_cols = max(10, event.width // self.cell_w)
        new_rows = max(5, event.height // self.cell_h)
        if new_cols != self.cols or new_rows != self.rows:
            self.cols = new_cols
            self.rows = new_rows
            self.canvas.delete("selection_box")
            self.selection.active = False
            self.session.resize(new_cols, new_rows)
            self.screen.mark_all_dirty()

    def _render_tick(self) -> None:
        self._tick_job = None
        if getattr(self, "_closed", False):
            return
        has_pending = self.session.drain_events()
        is_viewable = bool(self.winfo_viewable())

        if is_viewable:
            if self.search_state.query and self.screen.dirty_lines:
                matches = search_screen(self.screen, self.search_state.query)
                self.search_state.set_results(self.search_state.query, matches)
                self._update_search_ui(jump=False)

            self.renderer.render(self.screen, self.cols, self.rows)
            if self.search_state.matches:
                self.renderer.draw_search_matches(
                    self.search_state.matches, self.search_state.current_match, self.screen, self.cols, self.rows
                )
        else:
            self.screen.mark_all_dirty()

        try:
            delay = 1 if has_pending else (16 if is_viewable else 100)
            self._tick_job = self.after(delay, self._render_tick)
        except (tk.TclError, RuntimeError):
            pass

    def _on_title_changed(self, new_title: str) -> None:
        if self.on_title_change:
            self.on_title_change(self, new_title)

    def _on_session_close(self) -> None:
        if self.on_close:
            self.on_close(self)

    def _on_session_event(self) -> None:
        """Wake UI thread when background PTY events arrive without accumulating duplicate loops."""
        if getattr(self, "_closed", False):
            return
        # If a render tick is already scheduled, it will drain and render in <= 16ms (or 1ms).
        # We avoid cancelling/rescheduling from the background thread to prevent cross-thread timer races.
        if self._tick_job is None:
            try:
                self._tick_job = self.after_idle(self._render_tick)
            except (tk.TclError, OSError, RuntimeError):
                pass

    def _on_clipboard_write(self, selection: str, text: str) -> None:
        """Handle OSC 52 clipboard write."""
        if not getattr(self.config, "allow_clipboard_write", True):
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except (tk.TclError, OSError):
            pass

    def _on_clipboard_query(self, selection: str) -> str:
        """Handle OSC 52 clipboard query if security policy allows."""
        if not getattr(self.config, "allow_clipboard_read", False):
            return ""
        try:
            return self.clipboard_get()
        except (tk.TclError, OSError):
            return ""

    def _on_notification(self, title: str, message: str) -> None:
        """Handle desktop notification request (OSC 9 / OSC 777)."""
        try:
            self.bell()
        except (tk.TclError, OSError):
            pass

    def _on_bell(self) -> None:
        """Handle bell request from parser or OSC."""
        try:
            self.bell()
        except (tk.TclError, OSError):
            pass

    def has_foreground_process(self) -> bool:
        """Return True if a foreground process is running in this pane."""
        return self.session.has_foreground_process()

    def close(self) -> None:
        """Close this pane and clean up session and callbacks."""
        self._closed = True
        self.session.set_event_notifier(None)
        if self._tick_job:
            try:
                self.after_cancel(self._tick_job)
            except (tk.TclError, OSError, RuntimeError):
                pass
            self._tick_job = None
        self.session.close()
        try:
            self.destroy()
        except (tk.TclError, OSError, RuntimeError):
            pass
