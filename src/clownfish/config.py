"""Configuration options and user persistence for clownfish terminal emulator."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from clownfish.core.models import DEFAULT_BG, DEFAULT_FG


@dataclasses.dataclass
class TerminalConfig:
    """Configurable terminal options."""

    cols: int = 80
    rows: int = 24
    max_scrollback: int = 10_000
    font_family: str = "Menlo" if sys.platform == "darwin" else "Monospace"
    font_size: int = 13
    default_fg: tuple[int, int, int] = DEFAULT_FG
    default_bg: tuple[int, int, int] = DEFAULT_BG
    cursor_color: str = "#e5e5e5"
    selection_color: str = "#4a90e2"
    search_bg: str = "#d7ba7d"
    search_fg: str = "#141419"
    tab_bar_bg: str = "#18181c"
    tab_active_bg: str = "#282830"
    tab_fg: str = "#a0a0a8"
    tab_active_fg: str = "#ffffff"

    @staticmethod
    def default_config_path() -> Path:
        """Return the default configuration file location."""
        return Path.home() / ".config" / "clownfish" / "config.json"

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a JSON-serializable dictionary."""
        data = dataclasses.asdict(self)
        # Ensure tuples are converted to lists
        data["default_fg"] = list(self.default_fg)
        data["default_bg"] = list(self.default_bg)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TerminalConfig:
        """Create a TerminalConfig from a dictionary."""
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(cls):
            if f.name in data:
                val = data[f.name]
                if f.name in ("default_fg", "default_bg") and isinstance(val, (list, tuple)):
                    val = tuple(val[:3])
                kwargs[f.name] = val
        return cls(**kwargs)

    def save(self, path: Path | str | None = None) -> Path:
        """Save configuration to JSON file."""
        target_path = Path(path) if path is not None else self.default_config_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return target_path

    @classmethod
    def load(cls, path: Path | str | None = None) -> TerminalConfig:
        """Load configuration from JSON file, returning defaults if not found."""
        target_path = Path(path) if path is not None else cls.default_config_path()
        if not target_path.exists():
            return cls()
        try:
            with open(target_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return cls.from_dict(data)
        except (json.JSONDecodeError, OSError):
            pass
        return cls()
