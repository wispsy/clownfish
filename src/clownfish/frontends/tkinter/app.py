"""Tkinter-based terminal application window supporting tabs, splits, and search."""

from __future__ import annotations

import sys
import tkinter as tk
import webbrowser

from clownfish.config import TerminalConfig
from clownfish.frontends.tkinter.pane import TerminalPane
from clownfish.frontends.tkinter.settings import SettingsDialog
from clownfish.frontends.tkinter.tabs import TabbedTerminalView
from clownfish.session.session import TerminalSession


class TkTerminalApp:
    """Tkinter-based GUI terminal emulator application with tabs and split panes."""

    def __init__(
        self,
        root: tk.Tk,
        session: TerminalSession | None = None,
        cols: int = 80,
        rows: int = 24,
        config: TerminalConfig | None = None,
    ) -> None:
        self.root = root
        self.config = config or TerminalConfig.load()
        if cols != 80:
            self.config.cols = cols
        if rows != 24:
            self.config.rows = rows

        initial_title = session.title if session is not None else None
        auto_create = session is not None or not getattr(self.config, "restore_session", True)

        self.tab_view = TabbedTerminalView(
            self.root,
            config=self.config,
            on_title_changed=self._on_title_changed,
            on_all_closed=self._on_all_closed,
            initial_session=session,
            initial_title=initial_title,
            auto_create_tab=auto_create,
        )
        self.tab_view.pack(fill=tk.BOTH, expand=True)

        if session is None and getattr(self.config, "restore_session", True):
            from clownfish.session.persistence import SessionState

            saved_state = SessionState.load()
            if saved_state is not None:
                self.tab_view.load_state(saved_state)
            elif not self.tab_view.tabs:
                self.tab_view.new_tab()

        self._bind_shortcuts()
        self._build_menu()
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

    @property
    def active_pane(self) -> TerminalPane:
        """Return currently active terminal pane."""
        pane = self.tab_view.active_pane
        if pane is None:
            # Fallback if no pane
            split_view = self.tab_view.active_split_view
            if split_view and split_view.panes():
                return split_view.panes()[0]
            raise RuntimeError("No active terminal pane")
        return pane

    # Backwards compatibility proxies
    @property
    def session(self) -> TerminalSession:
        return self.active_pane.session

    @property
    def screen(self):
        return self.active_pane.screen

    @property
    def parser(self):
        return self.active_pane.parser

    @property
    def canvas(self) -> tk.Canvas:
        return self.active_pane.canvas

    @property
    def renderer(self):
        return self.active_pane.renderer

    @property
    def input_handler(self):
        return self.active_pane.input_handler

    @property
    def selection(self):
        return self.active_pane.selection

    @property
    def cols(self) -> int:
        return self.active_pane.cols

    @cols.setter
    def cols(self, val: int) -> None:
        self.active_pane.cols = val

    @property
    def rows(self) -> int:
        return self.active_pane.rows

    @rows.setter
    def rows(self, val: int) -> None:
        self.active_pane.rows = val

    @property
    def cell_w(self) -> int:
        return self.active_pane.cell_w

    @property
    def cell_h(self) -> int:
        return self.active_pane.cell_h

    def _bind_shortcuts(self) -> None:
        # Tab management
        self.root.bind("<Control-Shift-T>", lambda e: self._new_tab())
        self.root.bind("<Control-Shift-t>", lambda e: self._new_tab())
        self.root.bind("<Control-Shift-W>", lambda e: self._close_current())
        self.root.bind("<Control-Shift-w>", lambda e: self._close_current())

        if sys.platform == "darwin":
            self.root.bind("<Command-t>", lambda e: self._new_tab())
            self.root.bind("<Command-w>", lambda e: self._close_current())
            self.root.bind("<Command-n>", lambda e: self._new_window())
            self.root.bind("<Command-comma>", lambda e: self._open_settings_dialog())
            self.root.bind("<Command-Shift-O>", lambda e: self._open_ssh_dialog())
            self.root.bind("<Command-Shift-o>", lambda e: self._open_ssh_dialog())
            self.root.bind("<Command-d>", lambda e: self.split_vertical())
            self.root.bind("<Command-D>", lambda e: self.split_horizontal())
            self.root.bind("<Command-f>", lambda e: self._toggle_search())
            self.root.bind("<Command-k>", lambda e: self._clear_screen())
            self.root.bind("<Command-Option-k>", lambda e: self._clear_scrollback())
            self.root.bind("<Command-Option-K>", lambda e: self._clear_scrollback())
            self.root.bind("<Command-a>", lambda e: self._select_all())
            self.root.bind("<Command-A>", lambda e: self._select_all())
            self.root.bind("<Command-c>", self._copy_selection_to_clipboard)
            self.root.bind("<Command-v>", self._paste_from_clipboard)
            self.root.bind("<Command-bracketleft>", lambda e: self._prev_split())
            self.root.bind("<Command-bracketright>", lambda e: self._next_split())
            self.root.bind("<Command-equal>", lambda e: self._equalize_splits())
            self.root.bind("<Command-plus>", lambda e: self._zoom(1))
            self.root.bind("<Command-minus>", lambda e: self._zoom(-1))
            self.root.bind("<Command-Key-0>", lambda e: self._reset_zoom())
            self.root.bind("<Command-Up>", lambda e: self._jump_prompt(-1))
            self.root.bind("<Command-Down>", lambda e: self._jump_prompt(1))
            self.root.bind("<Command-Option-Up>", lambda e: self._scroll_view(1))
            self.root.bind("<Command-Option-Down>", lambda e: self._scroll_view(-1))
            self.root.bind("<Command-Home>", lambda e: self._scroll_view(100000))
            self.root.bind("<Command-End>", lambda e: self._scroll_view(-100000))
            self.root.bind("<Command-Option-l>", lambda e: self._announce_line())
            self.root.bind("<Command-Option-L>", lambda e: self._announce_line())
        else:
            self.root.bind("<Control-comma>", lambda e: self._open_settings_dialog())
            self.root.bind("<Control-Shift-N>", lambda e: self._new_window())
            self.root.bind("<Control-Shift-n>", lambda e: self._new_window())
            self.root.bind("<Control-Shift-O>", lambda e: self._open_ssh_dialog())
            self.root.bind("<Control-Shift-o>", lambda e: self._open_ssh_dialog())
            self.root.bind("<Control-Shift-D>", lambda e: self.split_vertical())
            self.root.bind("<Control-Shift-d>", lambda e: self.split_vertical())
            self.root.bind("<Control-Shift-F>", lambda e: self._toggle_search())
            self.root.bind("<Control-Shift-f>", lambda e: self._toggle_search())
            self.root.bind("<Control-Shift-K>", lambda e: self._clear_screen())
            self.root.bind("<Control-Shift-k>", lambda e: self._clear_screen())
            self.root.bind("<Control-Shift-C>", self._copy_selection_to_clipboard)
            self.root.bind("<Control-Shift-c>", self._copy_selection_to_clipboard)
            self.root.bind("<Control-Shift-V>", self._paste_from_clipboard)
            self.root.bind("<Control-Shift-v>", self._paste_from_clipboard)
            self.root.bind("<Control-Shift-A>", lambda e: self._select_all())
            self.root.bind("<Control-Shift-a>", lambda e: self._select_all())
            self.root.bind("<Alt-bracketleft>", lambda e: self._prev_split())
            self.root.bind("<Alt-bracketright>", lambda e: self._next_split())
            self.root.bind("<Control-equal>", lambda e: self._equalize_splits())
            self.root.bind("<Control-plus>", lambda e: self._zoom(1))
            self.root.bind("<Control-minus>", lambda e: self._zoom(-1))
            self.root.bind("<Control-Key-0>", lambda e: self._reset_zoom())
            self.root.bind("<Control-Up>", lambda e: self._jump_prompt(-1))
            self.root.bind("<Control-Down>", lambda e: self._jump_prompt(1))
            self.root.bind("<Control-Alt-l>", lambda e: self._announce_line())
            self.root.bind("<Control-Alt-L>", lambda e: self._announce_line())

        # Tab switching
        self.root.bind("<Control-Tab>", lambda e: self._next_tab())
        self.root.bind("<Control-Shift-Tab>", lambda e: self._prev_tab())
        self.root.bind("<Control-ISO_Left_Tab>", lambda e: self._prev_tab())

        for i in range(1, 10):
            if sys.platform == "darwin":
                self.root.bind(
                    f"<Command-Key-{i}>", lambda e, idx=i - 1: self.tab_view.switch_tab(idx)
                )
            else:
                self.root.bind(f"<Alt-Key-{i}>", lambda e, idx=i - 1: self.tab_view.switch_tab(idx))

    def _new_tab(self) -> str:
        self.tab_view.new_tab()
        return "break"

    def _close_current(self) -> str:
        if getattr(self.config, "confirm_close_active_process", True):
            try:
                pane = self.active_pane
                if pane and pane.has_foreground_process():
                    from tkinter import messagebox

                    if not messagebox.askyesno(
                        "Close Terminal?",
                        "A process is currently running in this terminal.\nClosing it will terminate the process. Close anyway?",
                        parent=self.root,
                    ):
                        return "break"
            except tk.TclError, OSError:
                return "break"

        split_view = self.tab_view.active_split_view
        if split_view and len(split_view.panes()) > 1:
            split_view.close_pane(self.active_pane)
        else:
            self.tab_view.close_tab()
        return "break"

    def _next_tab(self) -> str:
        self.tab_view.next_tab()
        return "break"

    def _prev_tab(self) -> str:
        self.tab_view.prev_tab()
        return "break"

    def split_horizontal(self) -> str:
        """Split active pane horizontally (side-by-side)."""
        sv = self.tab_view.active_split_view
        if sv:
            sv.split_horizontal(self.active_pane)
        return "break"

    def split_vertical(self) -> str:
        """Split active pane vertically (top-and-bottom)."""
        sv = self.tab_view.active_split_view
        if sv:
            sv.split_vertical(self.active_pane)
        return "break"

    def _next_split(self) -> str:
        sv = self.tab_view.active_split_view
        if sv:
            sv.focus_next_pane()
        return "break"

    def _prev_split(self) -> str:
        sv = self.tab_view.active_split_view
        if sv:
            sv.focus_prev_pane()
        return "break"

    def _equalize_splits(self) -> str:
        sv = self.tab_view.active_split_view
        if sv:
            sv.equalize_splits()
        return "break"

    def _toggle_search(self) -> str:
        try:
            self.active_pane.toggle_search()
        except RuntimeError:
            pass
        return "break"

    def _clear_screen(self) -> str:
        try:
            pane = self.active_pane
            pane.session.clear()
            pane.selection.active = False
        except RuntimeError:
            pass
        return "break"

    def _jump_prompt(self, direction: int) -> str:
        try:
            pane = self.active_pane
            new_offset = pane.session.jump_prompt(direction)
            if new_offset is not None:
                pane.canvas.delete("selection_box")
                pane.selection.active = False
        except RuntimeError:
            pass
        return "break"

    def _copy_selection_to_clipboard(self, event: tk.Event | None = None) -> str:
        try:
            pane = self.active_pane
            sel = pane.selection
            if sel.is_empty():
                return "break"

            (c1, r1), (c2, r2) = sel.normalized()
            lines = []
            for r in range(r1, r2 + 1):
                row_cells = pane.screen.get_visible_row(r)
                sc = c1 if r == r1 else 0
                ec = c2 if r == r2 else pane.cols - 1
                line_text = "".join(cell.char for cell in row_cells[sc : ec + 1] if cell.width != 0)
                lines.append(line_text.rstrip())

            selected_text = "\n".join(lines)
            if selected_text:
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                self.root.update()
        except RuntimeError, tk.TclError:
            pass
        return "break"

    def _paste_from_clipboard(self, event: tk.Event | None = None) -> str:
        try:
            clipboard_text = self.root.clipboard_get()
            if not clipboard_text:
                return "break"
            if getattr(self.config, "confirm_multiline_paste", False) and "\n" in clipboard_text:
                from tkinter import messagebox

                line_count = clipboard_text.count("\n") + 1
                preview = clipboard_text.strip()
                if len(preview) > 150:
                    preview = preview[:150] + "..."
                if not messagebox.askyesno(
                    "Confirm Multiline Paste",
                    f"You are about to paste {line_count} lines into the terminal:\n\n{preview}\n\nDo you want to continue?",
                    parent=self.root,
                ):
                    return "break"
            self.active_pane.session.paste(clipboard_text)
        except RuntimeError, tk.TclError:
            pass
        return "break"

    def _on_title_changed(self, new_title: str) -> None:
        try:
            self.root.title(f"{new_title} - clownfish")
        except tk.TclError:
            pass

    def _open_ssh_dialog(self) -> str:
        """Open modal dialog to connect to an SSH host in a new tab."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Connect to Remote Host (SSH)")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg="#18181c")
        dialog.resizable(False, False)

        tk.Label(
            dialog,
            text="Remote Destination (host or user@host):",
            bg="#18181c",
            fg="#e5e5e5",
            font=("Helvetica", 11),
        ).pack(anchor=tk.W, padx=16, pady=(12, 4))
        dest_entry = tk.Entry(
            dialog,
            bg="#282830",
            fg="#ffffff",
            insertbackground="#ffffff",
            width=36,
            font=("Helvetica", 11),
        )
        dest_entry.pack(fill=tk.X, padx=16)
        dest_entry.focus_set()

        tk.Label(
            dialog,
            text="Port (optional, default 22):",
            bg="#18181c",
            fg="#e5e5e5",
            font=("Helvetica", 11),
        ).pack(anchor=tk.W, padx=16, pady=(8, 4))
        port_entry = tk.Entry(
            dialog,
            bg="#282830",
            fg="#ffffff",
            insertbackground="#ffffff",
            width=36,
            font=("Helvetica", 11),
        )
        port_entry.insert(0, "22")
        port_entry.pack(fill=tk.X, padx=16)

        tk.Label(
            dialog,
            text="Identity File (optional):",
            bg="#18181c",
            fg="#e5e5e5",
            font=("Helvetica", 11),
        ).pack(anchor=tk.W, padx=16, pady=(8, 4))
        id_entry = tk.Entry(
            dialog,
            bg="#282830",
            fg="#ffffff",
            insertbackground="#ffffff",
            width=36,
            font=("Helvetica", 11),
        )
        id_entry.pack(fill=tk.X, padx=16)

        btn_frame = tk.Frame(dialog, bg="#18181c")
        btn_frame.pack(fill=tk.X, padx=16, pady=(16, 12))

        def do_connect():
            dest = dest_entry.get().strip()
            if not dest:
                return
            port_val = port_entry.get().strip()
            port = int(port_val) if port_val.isdigit() else 22
            id_val = id_entry.get().strip() or None

            user = None
            host = dest
            if "@" in dest:
                user, host = dest.split("@", 1)

            dialog.destroy()
            self.tab_view.new_ssh_tab(
                host=host,
                user=user,
                port=port,
                identity_file=id_val,
            )

        connect_btn = tk.Button(
            btn_frame,
            text="Connect",
            bg="#4a90e2",
            fg="#ffffff",
            activebackground="#357abd",
            command=do_connect,
            relief=tk.FLAT,
            padx=12,
            pady=4,
        )
        connect_btn.pack(side=tk.RIGHT, padx=(8, 0))

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            bg="#282830",
            fg="#e5e5e5",
            command=dialog.destroy,
            relief=tk.FLAT,
            padx=12,
            pady=4,
        )
        cancel_btn.pack(side=tk.RIGHT)

        dialog.bind("<Return>", lambda e: do_connect())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        return "break"

    def _on_all_closed(self) -> None:
        self._on_window_close()

    def _on_window_close(self) -> None:
        if getattr(self.config, "confirm_close_active_process", True):
            has_active = any(
                pane.has_foreground_process() for _, sv in self.tab_view.tabs for pane in sv.panes()
            )
            if has_active:
                from tkinter import messagebox

                if not messagebox.askyesno(
                    "Quit Clownfish?",
                    "One or more processes are currently running in your terminal tabs.\nClosing the window will terminate them. Quit anyway?",
                    parent=self.root,
                ):
                    return

        if getattr(self.config, "restore_session", True):
            try:
                state = self.tab_view.dump_state()
                state.save()
            except OSError, tk.TclError:
                pass

        for _, sv in self.tab_view.tabs:
            for pane in sv.panes():
                pane.close()
        try:
            self.root.destroy()
        except tk.TclError, OSError:
            pass

    def _build_menu(self) -> None:
        """Build native application menubar."""
        menubar = tk.Menu(self.root)

        # Clownfish / File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(
            label="New Window",
            command=self._new_window,
            accelerator="Cmd+N" if sys.platform == "darwin" else "Ctrl+Shift+N",
        )
        file_menu.add_command(
            label="New Tab",
            command=self._new_tab,
            accelerator="Cmd+T" if sys.platform == "darwin" else "Ctrl+Shift+T",
        )
        file_menu.add_command(
            label="Connect to Remote Host (SSH)...",
            command=self._open_ssh_dialog,
            accelerator="Cmd+Shift+O" if sys.platform == "darwin" else "Ctrl+Shift+O",
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Settings...",
            command=self._open_settings_dialog,
            accelerator="Cmd+," if sys.platform == "darwin" else "Ctrl+,",
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Close Tab / Split",
            command=self._close_current,
            accelerator="Cmd+W" if sys.platform == "darwin" else "Ctrl+Shift+W",
        )
        file_menu.add_command(
            label="Quit Clownfish",
            command=self._on_window_close,
            accelerator="Cmd+Q" if sys.platform == "darwin" else "Ctrl+Q",
        )
        menubar.add_cascade(
            label="Clownfish" if sys.platform == "darwin" else "File", menu=file_menu
        )

        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(
            label="Copy",
            command=self._copy_selection_to_clipboard,
            accelerator="Cmd+C" if sys.platform == "darwin" else "Ctrl+Shift+C",
        )
        edit_menu.add_command(
            label="Paste",
            command=self._paste_from_clipboard,
            accelerator="Cmd+V" if sys.platform == "darwin" else "Ctrl+Shift+V",
        )
        edit_menu.add_command(
            label="Select All",
            command=self._select_all,
            accelerator="Cmd+A" if sys.platform == "darwin" else "Ctrl+Shift+A",
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Find...",
            command=self._toggle_search,
            accelerator="Cmd+F" if sys.platform == "darwin" else "Ctrl+Shift+F",
        )
        edit_menu.add_separator()
        edit_menu.add_command(
            label="Clear Screen",
            command=self._clear_screen,
            accelerator="Cmd+K" if sys.platform == "darwin" else "Ctrl+Shift+K",
        )
        edit_menu.add_command(
            label="Clear Scrollback Buffer",
            command=self._clear_scrollback,
            accelerator="Cmd+Opt+K" if sys.platform == "darwin" else "Ctrl+Alt+K",
        )
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(
            label="Zoom In",
            command=lambda: self._zoom(1),
            accelerator="Cmd++" if sys.platform == "darwin" else "Ctrl++",
        )
        view_menu.add_command(
            label="Zoom Out",
            command=lambda: self._zoom(-1),
            accelerator="Cmd+-" if sys.platform == "darwin" else "Ctrl+-",
        )
        view_menu.add_command(
            label="Actual Size",
            command=self._reset_zoom,
            accelerator="Cmd+0" if sys.platform == "darwin" else "Ctrl+0",
        )
        view_menu.add_separator()
        view_menu.add_command(
            label="Split Pane Vertically",
            command=self.split_vertical,
            accelerator="Cmd+D" if sys.platform == "darwin" else "Ctrl+Shift+D",
        )
        view_menu.add_command(
            label="Split Pane Horizontally",
            command=self.split_horizontal,
            accelerator="Cmd+Shift+D",
        )
        view_menu.add_command(
            label="Equalize Splits",
            command=self._equalize_splits,
            accelerator="Cmd+=" if sys.platform == "darwin" else "Ctrl+=",
        )
        view_menu.add_separator()
        view_menu.add_command(label="Toggle Scrollbar", command=self._toggle_scrollbar)
        view_menu.add_command(label="Toggle Screen Reader Mode", command=self._toggle_screen_reader)
        menubar.add_cascade(label="View", menu=view_menu)

        # Window Menu
        window_menu = tk.Menu(menubar, tearoff=0)
        window_menu.add_command(label="Next Tab", command=self._next_tab, accelerator="Ctrl+Tab")
        window_menu.add_command(
            label="Previous Tab", command=self._prev_tab, accelerator="Ctrl+Shift+Tab"
        )
        window_menu.add_separator()
        window_menu.add_command(
            label="Next Split Pane",
            command=self._next_split,
            accelerator="Cmd+]" if sys.platform == "darwin" else "Alt+]",
        )
        window_menu.add_command(
            label="Previous Split Pane",
            command=self._prev_split,
            accelerator="Cmd+[" if sys.platform == "darwin" else "Alt+[",
        )
        menubar.add_cascade(label="Window", menu=window_menu)

        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="Clownfish Documentation",
            command=lambda: webbrowser.open("https://github.com/wispsy/clownfish"),
        )
        help_menu.add_command(
            label="Speak Current Line",
            command=self._announce_line,
            accelerator="Cmd+Opt+L" if sys.platform == "darwin" else "Ctrl+Alt+L",
        )
        help_menu.add_separator()
        help_menu.add_command(label="About Clownfish", command=self._show_about_dialog)
        menubar.add_cascade(label="Help", menu=help_menu)

        try:
            self.root.config(menu=menubar)
        except tk.TclError:
            pass

    def _open_settings_dialog(self) -> str:
        """Open settings dialog window."""
        SettingsDialog(self.root, self.config, on_apply=self.apply_config)
        return "break"

    def apply_config(self, new_config: TerminalConfig) -> None:
        """Apply new configuration to application and all tabs/panes."""
        self.config = new_config
        self.tab_view.apply_config(new_config)

    def _scroll_view(self, delta: int) -> str:
        try:
            self.active_pane.screen.scroll_view(delta)
        except RuntimeError:
            pass
        return "break"

    def _clear_scrollback(self) -> str:
        try:
            self.active_pane.session.clear_scrollback()
        except RuntimeError:
            pass
        return "break"

    def _zoom(self, delta: int) -> str:
        new_size = max(6, min(72, self.config.font_size + delta))
        if new_size != self.config.font_size:
            self.config.font_size = new_size
            self.apply_config(self.config)
        return "break"

    def _reset_zoom(self) -> str:
        default_size = 13
        if self.config.font_size != default_size:
            self.config.font_size = default_size
            self.apply_config(self.config)
        return "break"

    def _announce_line(self) -> str:
        try:
            self.active_pane.announce_current_line()
        except RuntimeError:
            pass
        return "break"

    def _select_all(self) -> str:
        try:
            pane = self.active_pane
            pane.selection.start = (0, 0)
            pane.selection.end = (pane.cols - 1, pane.rows - 1)
            pane.selection.active = True
            pane.screen.mark_all_dirty()
        except RuntimeError:
            pass
        return "break"

    def _toggle_scrollbar(self) -> None:
        self.config.show_scrollbar = not getattr(self.config, "show_scrollbar", True)
        self.apply_config(self.config)

    def _toggle_screen_reader(self) -> None:
        self.config.screen_reader_mode = not getattr(self.config, "screen_reader_mode", False)
        self.apply_config(self.config)
        status = "enabled" if self.config.screen_reader_mode else "disabled"
        try:
            self.active_pane.a11y_bridge.announce(f"Screen reader mode {status}")
        except RuntimeError:
            pass

    def _show_about_dialog(self) -> None:
        from tkinter import messagebox

        import clownfish

        messagebox.showinfo(
            "About Clownfish",
            f"Clownfish Terminal Emulator\nVersion {clownfish.__version__}\n\n"
            "A fast, modern terminal emulator written in pure Python.\n"
            "https://github.com/wispsy/clownfish",
            parent=self.root,
        )

    def _new_window(self) -> str:
        import subprocess

        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable, "-m", "clownfish"])
        except OSError, tk.TclError:
            pass
        return "break"
