"""Preferences and Settings modal dialog for Clownfish terminal."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from clownfish.config import TerminalConfig
from clownfish.themes import THEMES, apply_theme_to_config, list_themes


class SettingsDialog(tk.Toplevel):
    """Preferences and settings configuration dialog."""

    def __init__(
        self,
        parent: tk.Tk,
        config: TerminalConfig,
        on_apply: Callable[[TerminalConfig], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_apply = on_apply
        self.title("Preferences - Clownfish")
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#18181c")
        self.geometry("560x520")
        self.minsize(520, 480)

        self._init_ui()
        self.bind("<Escape>", lambda e: self.destroy())

    def _init_ui(self) -> None:
        # Style notebook
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        tab_appearance = tk.Frame(notebook, bg="#1e1e24", padx=16, pady=16)
        tab_themes = tk.Frame(notebook, bg="#1e1e24", padx=16, pady=16)
        tab_behavior = tk.Frame(notebook, bg="#1e1e24", padx=16, pady=16)

        notebook.add(tab_appearance, text="Appearance")
        notebook.add(tab_themes, text="Themes")
        notebook.add(tab_behavior, text="Behavior & A11y")

        # --- Appearance Tab ---
        self._build_appearance_tab(tab_appearance)

        # --- Themes Tab ---
        self._build_themes_tab(tab_themes)

        # --- Behavior & A11y Tab ---
        self._build_behavior_tab(tab_behavior)

        # Button Bar
        btn_frame = tk.Frame(self, bg="#18181c")
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))

        save_btn = tk.Button(
            btn_frame,
            text="Save & Apply",
            bg="#4a90e2",
            fg="#ffffff",
            activebackground="#357abd",
            command=self._on_save,
            relief=tk.FLAT,
            padx=14,
            pady=5,
        )
        save_btn.pack(side=tk.RIGHT, padx=(8, 0))

        cancel_btn = tk.Button(
            btn_frame,
            text="Cancel",
            bg="#282830",
            fg="#cccccc",
            command=self.destroy,
            relief=tk.FLAT,
            padx=12,
            pady=5,
        )
        cancel_btn.pack(side=tk.RIGHT)

    def _build_appearance_tab(self, parent: tk.Frame) -> None:
        row = 0
        tk.Label(parent, text="Font Family:", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.font_family_var = tk.StringVar(value=self.config.font_family)
        font_choices = [
            "Menlo",
            "Monaco",
            "Courier",
            "SF Mono",
            "Fira Code",
            "JetBrains Mono",
            "Consolas",
        ]
        font_cb = ttk.Combobox(
            parent, textvariable=self.font_family_var, values=font_choices, width=22
        )
        font_cb.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        tk.Label(parent, text="Font Size:", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.font_size_var = tk.IntVar(value=self.config.font_size)
        size_sp = tk.Spinbox(
            parent,
            from_=9,
            to=36,
            textvariable=self.font_size_var,
            width=6,
            bg="#282830",
            fg="#ffffff",
        )
        size_sp.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        tk.Label(parent, text="Padding X (Horizontal margin):", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.pad_x_var = tk.IntVar(value=getattr(self.config, "padding_x", 8))
        padx_sp = tk.Spinbox(
            parent, from_=0, to=48, textvariable=self.pad_x_var, width=6, bg="#282830", fg="#ffffff"
        )
        padx_sp.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        tk.Label(parent, text="Padding Y (Vertical margin):", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.pad_y_var = tk.IntVar(value=getattr(self.config, "padding_y", 6))
        pady_sp = tk.Spinbox(
            parent, from_=0, to=48, textvariable=self.pad_y_var, width=6, bg="#282830", fg="#ffffff"
        )
        pady_sp.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        tk.Label(parent, text="Cursor Color:", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.cursor_color_var = tk.StringVar(value=self.config.cursor_color)
        cursor_entry = tk.Entry(
            parent, textvariable=self.cursor_color_var, width=12, bg="#282830", fg="#ffffff"
        )
        cursor_entry.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        self.show_scrollbar_var = tk.BooleanVar(value=getattr(self.config, "show_scrollbar", True))
        sb_chk = tk.Checkbutton(
            parent,
            text="Show vertical scrollbar",
            variable=self.show_scrollbar_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        sb_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

        row += 1
        self.ligatures_var = tk.BooleanVar(value=getattr(self.config, "enable_ligatures", False))
        lig_chk = tk.Checkbutton(
            parent,
            text="Enable programming ligatures (->, =>, ===, !==)",
            variable=self.ligatures_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        lig_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

    def _build_themes_tab(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="Select Color Theme:",
            bg="#1e1e24",
            fg="#dddddd",
            font=("Helvetica", 11, "bold"),
        ).pack(anchor=tk.W, pady=(0, 8))

        self.theme_var = tk.StringVar(value=getattr(self.config, "theme", "clownfish_dark"))
        themes = list_themes()

        preview_frame = tk.Frame(parent, bg="#1e1e24")
        preview_frame.pack(fill=tk.BOTH, expand=True)

        for key, display_name in themes:
            t = THEMES[key]
            r_frame = tk.Frame(preview_frame, bg="#1e1e24", pady=4)
            r_frame.pack(fill=tk.X)

            rb = tk.Radiobutton(
                r_frame,
                text=display_name,
                variable=self.theme_var,
                value=key,
                bg="#1e1e24",
                fg="#ffffff",
                selectcolor="#282830",
                activebackground="#1e1e24",
                font=("Helvetica", 11),
                command=lambda k=key: self._on_theme_selected(k),
            )
            rb.pack(side=tk.LEFT, padx=(0, 16))

            # Color swatches
            swatch_bg = f"#{t.default_bg[0]:02x}{t.default_bg[1]:02x}{t.default_bg[2]:02x}"
            swatch_fg = f"#{t.default_fg[0]:02x}{t.default_fg[1]:02x}{t.default_fg[2]:02x}"
            sw1 = tk.Label(
                r_frame,
                text=" BG ",
                bg=swatch_bg,
                fg=swatch_fg,
                relief=tk.SOLID,
                bd=1,
                font=("Helvetica", 9),
            )
            sw1.pack(side=tk.LEFT, padx=2)
            sw2 = tk.Label(
                r_frame,
                text=" Cursor ",
                bg=t.cursor_color,
                fg=swatch_bg,
                relief=tk.SOLID,
                bd=1,
                font=("Helvetica", 9),
            )
            sw2.pack(side=tk.LEFT, padx=2)
            sw3 = tk.Label(
                r_frame,
                text=" Select ",
                bg=t.selection_color,
                fg="#ffffff",
                relief=tk.SOLID,
                bd=1,
                font=("Helvetica", 9),
            )
            sw3.pack(side=tk.LEFT, padx=2)

    def _on_theme_selected(self, theme_key: str) -> None:
        apply_theme_to_config(self.config, theme_key)
        self.cursor_color_var.set(self.config.cursor_color)

    def _build_behavior_tab(self, parent: tk.Frame) -> None:
        row = 0
        tk.Label(parent, text="Scrollback Buffer Lines:", bg="#1e1e24", fg="#dddddd").grid(
            row=row, column=0, sticky=tk.W, pady=6
        )
        self.scrollback_var = tk.IntVar(value=self.config.max_scrollback)
        sb_sp = tk.Spinbox(
            parent,
            from_=1000,
            to=100000,
            increment=1000,
            textvariable=self.scrollback_var,
            width=10,
            bg="#282830",
            fg="#ffffff",
        )
        sb_sp.grid(row=row, column=1, sticky=tk.W, pady=6, padx=8)

        row += 1
        self.restore_session_var = tk.BooleanVar(
            value=getattr(self.config, "restore_session", True)
        )
        rest_chk = tk.Checkbutton(
            parent,
            text="Restore open tabs and splits on launch",
            variable=self.restore_session_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        rest_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

        row += 1
        self.confirm_close_var = tk.BooleanVar(
            value=getattr(self.config, "confirm_close_active_process", True)
        )
        close_chk = tk.Checkbutton(
            parent,
            text="Confirm before closing windows with running processes",
            variable=self.confirm_close_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        close_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

        row += 1
        self.multiline_paste_var = tk.BooleanVar(
            value=getattr(self.config, "confirm_multiline_paste", False)
        )
        paste_chk = tk.Checkbutton(
            parent,
            text="Confirm before pasting multiple lines",
            variable=self.multiline_paste_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        paste_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

        row += 1
        self.screen_reader_var = tk.BooleanVar(
            value=getattr(self.config, "screen_reader_mode", False)
        )
        a11y_chk = tk.Checkbutton(
            parent,
            text="Enable Screen Reader speech & accessibility announcements",
            variable=self.screen_reader_var,
            bg="#1e1e24",
            fg="#dddddd",
            selectcolor="#282830",
            activebackground="#1e1e24",
        )
        a11y_chk.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=6)

    def _on_save(self) -> None:
        self.config.font_family = self.font_family_var.get().strip() or "Menlo"
        self.config.font_size = max(8, min(48, self.font_size_var.get()))
        self.config.padding_x = max(0, min(64, self.pad_x_var.get()))
        self.config.padding_y = max(0, min(64, self.pad_y_var.get()))
        self.config.cursor_color = self.cursor_color_var.get().strip() or "#e5e5e5"
        self.config.show_scrollbar = self.show_scrollbar_var.get()
        self.config.enable_ligatures = self.ligatures_var.get()
        self.config.max_scrollback = max(500, self.scrollback_var.get())
        self.config.restore_session = self.restore_session_var.get()
        self.config.confirm_close_active_process = self.confirm_close_var.get()
        self.config.confirm_multiline_paste = self.multiline_paste_var.get()
        self.config.screen_reader_mode = self.screen_reader_var.get()

        selected_theme = self.theme_var.get()
        apply_theme_to_config(self.config, selected_theme)

        # Persist to disk
        try:
            self.config.save()
        except OSError:
            pass

        if self.on_apply:
            self.on_apply(self.config)

        self.destroy()
