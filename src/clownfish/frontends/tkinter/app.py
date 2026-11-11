"""Tkinter-based terminal application window."""

from __future__ import annotations

import sys
import tkinter as tk

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.input import TkInputHandler
from clownfish.frontends.tkinter.renderer import TkCanvasRenderer
from clownfish.session.session import TerminalSession


class TkTerminalApp:
    """Tkinter-based GUI terminal emulator connected to a TerminalSession."""

    def __init__(
        self,
        root: tk.Tk,
        session: TerminalSession | None = None,
        cols: int = 80,
        rows: int = 24,
        config: TerminalConfig | None = None,
    ) -> None:
        self.root = root
        self.config = config or TerminalConfig(cols=cols, rows=rows)
        self.cols = cols
        self.rows = rows
        self._resize_job: str | None = None

        self.session = session or TerminalSession(
            cols=cols,
            rows=rows,
            max_scrollback=self.config.max_scrollback,
            on_title_changed=self._on_title_changed,
            on_close=self._on_session_close,
        )
        self.session.on_title_changed = self._on_title_changed
        self.session.on_close = self._on_session_close

        # Compatibility proxies
        self.screen = self.session.screen
        self.parser = self.session.parser

        self.canvas = tk.Canvas(
            root,
            width=self.cols * 8,
            height=self.rows * 16,
            bg=TkCanvasRenderer.rgb_to_hex(self.config.default_bg),
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.renderer = TkCanvasRenderer(self.canvas, self.config)
        self.cell_w = self.renderer.cell_w
        self.cell_h = self.renderer.cell_h
        self.canvas.config(width=self.cols * self.cell_w, height=self.rows * self.cell_h)

        self.input_handler = TkInputHandler(self.session)
        self.selection = self.input_handler.selection

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._bind_events()
        self.session.start()
        self._render_tick()

    def _bind_events(self) -> None:
        # Mouse & Pointer Interactions
        self.canvas.bind("<Button-1>", self._on_button_1_press)
        self.canvas.bind("<B1-Motion>", self._on_button_1_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_1_release)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.canvas.bind("<Triple-Button-1>", self._on_triple_click)
        self.canvas.bind("<Motion>", self._on_pointer_motion)

        # Mouse Wheel & Buttons
        self.canvas.bind("<Button-4>", lambda e: self._on_mouse_scroll(-3, e))
        self.canvas.bind("<Button-5>", lambda e: self._on_mouse_scroll(3, e))
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # Keyboard & Window Events
        self.canvas.bind("<KeyPress>", self._on_key_press)
        self.canvas.focus_set()
        self.root.bind("<Configure>", self._on_window_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Copy & Paste
        self.root.bind("<Control-Shift-C>", self._copy_selection_to_clipboard)
        self.root.bind("<Control-Shift-c>", self._copy_selection_to_clipboard)
        self.root.bind("<Control-Shift-V>", self._paste_from_clipboard)
        self.root.bind("<Control-Shift-v>", self._paste_from_clipboard)
        if sys.platform == "darwin":
            self.root.bind("<Command-c>", self._copy_selection_to_clipboard)
            self.root.bind("<Command-v>", self._paste_from_clipboard)
        self.canvas.bind("<Button-2>", lambda e: self._paste_from_clipboard())

        # Clear screen shortcuts
        if sys.platform == "darwin":
            self.root.bind("<Command-k>", self._on_clear_screen_shortcut)
            self.root.bind("<Command-K>", self._on_clear_screen_shortcut)
        else:
            self.root.bind("<Control-Shift-k>", self._on_clear_screen_shortcut)
            self.root.bind("<Control-Shift-K>", self._on_clear_screen_shortcut)

        # Semantic prompt jumping (OSC 133)
        self.canvas.bind("<Command-Up>", lambda e: self._jump_prompt(-1))
        self.canvas.bind("<Command-Down>", lambda e: self._jump_prompt(1))
        self.canvas.bind("<Control-Up>", lambda e: self._jump_prompt(-1))
        self.canvas.bind("<Control-Down>", lambda e: self._jump_prompt(1))

    # --- Mouse Event Forwarding ---

    def _on_button_1_press(self, event: tk.Event) -> None:
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

    def _on_key_press(self, event: tk.Event) -> str:
        return self.input_handler.on_key_press(event, self.canvas)

    # --- Clipboard & Shortcuts ---

    def _copy_selection_to_clipboard(self, event: tk.Event | None = None) -> str:
        sel = self.input_handler.selection
        if sel.is_empty():
            return "break"

        (c1, r1), (c2, r2) = sel.normalized()
        lines = []

        for r in range(r1, r2 + 1):
            row_cells = self.screen.get_visible_row(r)
            sc = c1 if r == r1 else 0
            ec = c2 if r == r2 else self.cols - 1
            line_text = "".join(cell.char for cell in row_cells[sc : ec + 1] if cell.width != 0)
            lines.append(line_text.rstrip())

        selected_text = "\n".join(lines)
        if selected_text:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_text)
            self.root.update()

        return "break"

    def _paste_from_clipboard(self, event: tk.Event | None = None) -> str:
        try:
            clipboard_text = self.root.clipboard_get()
        except tk.TclError:
            return "break"

        if clipboard_text:
            self.session.paste(clipboard_text)

        return "break"

    def _on_clear_screen_shortcut(self, event: tk.Event | None = None) -> str:
        self.session.clear()
        self.canvas.delete("all")
        self.input_handler.selection.active = False
        return "break"

    def _jump_prompt(self, direction: int) -> str:
        new_offset = self.session.jump_prompt(direction)
        if new_offset is not None:
            self.canvas.delete("selection_box")
            self.input_handler.selection.active = False
        return "break"

    # --- Resize & Render Tick ---

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget != self.root:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(50, self._apply_resize, event.width, event.height)

    def _apply_resize(self, width: int, height: int) -> None:
        self._resize_job = None
        new_cols = max(10, width // self.cell_w)
        new_rows = max(5, height // self.cell_h)

        if new_cols == self.cols and new_rows == self.rows:
            return

        self.cols = new_cols
        self.rows = new_rows
        self.canvas.delete("selection_box")
        self.input_handler.selection.active = False
        self.session.resize(new_cols, new_rows)
        self.canvas.delete("all")
        self.screen.mark_all_dirty()

    def _render_tick(self) -> None:
        self.renderer.render(self.screen, self.cols, self.rows)
        try:
            self.root.after(16, self._render_tick)
        except tk.TclError:
            pass

    def _on_title_changed(self, new_title: str) -> None:
        try:
            self.root.title(new_title)
        except tk.TclError:
            pass

    def _on_session_close(self) -> None:
        self._on_close()

    def _on_close(self) -> None:
        self.session.close()
        try:
            self.root.destroy()
        except (tk.TclError, OSError):
            pass
