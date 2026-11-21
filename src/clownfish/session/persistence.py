"""Session layout persistence and state serialization for Clownfish."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class PaneState:
    """State for an individual terminal pane."""

    cwd: str | None = None
    title: str = "clownfish"
    ssh: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cwd": self.cwd,
            "title": self.title,
            "ssh": self.ssh,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaneState:
        return cls(
            cwd=data.get("cwd"),
            title=data.get("title", "clownfish"),
            ssh=data.get("ssh"),
        )


@dataclasses.dataclass
class SplitNodeState:
    """Node in the recursive split hierarchy (either leaf pane or split container)."""

    is_leaf: bool = True
    orientation: str = "horizontal"  # "horizontal" or "vertical"
    children: list[SplitNodeState] = dataclasses.field(default_factory=list)
    pane: PaneState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_leaf": self.is_leaf,
            "orientation": self.orientation,
            "children": [c.to_dict() for c in self.children],
            "pane": self.pane.to_dict() if self.pane else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SplitNodeState:
        children = [cls.from_dict(c) for c in data.get("children", [])]
        pane_data = data.get("pane")
        pane = PaneState.from_dict(pane_data) if pane_data else None
        return cls(
            is_leaf=data.get("is_leaf", True),
            orientation=data.get("orientation", "horizontal"),
            children=children,
            pane=pane,
        )


@dataclasses.dataclass
class TabState:
    """State of an individual terminal tab."""

    title: str = "Terminal"
    root: SplitNodeState = dataclasses.field(default_factory=SplitNodeState)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "root": self.root.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TabState:
        root_data = data.get("root", {})
        return cls(
            title=data.get("title", "Terminal"),
            root=SplitNodeState.from_dict(root_data),
        )


@dataclasses.dataclass
class SessionState:
    """Overall session state including all tabs and active index."""

    version: int = 1
    active_tab_index: int = 0
    tabs: list[TabState] = dataclasses.field(default_factory=list)

    @staticmethod
    def default_state_path() -> Path:
        """Return the default session state JSON file location."""
        return Path.home() / ".config" / "clownfish" / "session_state.json"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "active_tab_index": self.active_tab_index,
            "tabs": [t.to_dict() for t in self.tabs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionState:
        tabs = [TabState.from_dict(t) for t in data.get("tabs", [])]
        return cls(
            version=data.get("version", 1),
            active_tab_index=data.get("active_tab_index", 0),
            tabs=tabs,
        )

    def save(self, path: Path | str | None = None) -> Path:
        """Save session state to JSON file."""
        target_path = Path(path) if path is not None else self.default_state_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        return target_path

    @classmethod
    def load(cls, path: Path | str | None = None) -> SessionState | None:
        """Load session state from JSON file, returning None if absent or invalid."""
        target_path = Path(path) if path is not None else cls.default_state_path()
        if not target_path.exists():
            return None
        try:
            with open(target_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "tabs" in data:
                return cls.from_dict(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None
