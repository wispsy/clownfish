"""Session layout persistence and state serialization for Clownfish.

Note:
    SessionState captures the visual workspace layout (tab titles, recursive split
    trees, working directories, and SSH destination parameters). On restoration,
    Clownfish creates fresh shell processes and (optionally) new SSH connections;
    it does not preserve live remote process states, running background daemons, or
    foreground child processes.
"""

from __future__ import annotations

import dataclasses
import json
import os
import tempfile
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
    def from_dict(cls, data: Any) -> PaneState:
        if not isinstance(data, dict):
            return cls()
        cwd = data.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            cwd = None
        title = data.get("title", "clownfish")
        if not isinstance(title, str):
            title = "clownfish"
        ssh = data.get("ssh")
        if ssh is not None and not isinstance(ssh, dict):
            ssh = None
        return cls(cwd=cwd, title=title, ssh=ssh)


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
    def from_dict(cls, data: Any) -> SplitNodeState:
        if not isinstance(data, dict):
            return cls(is_leaf=True, pane=PaneState())

        is_leaf = bool(data.get("is_leaf", True))
        orientation = data.get("orientation", "horizontal")
        if orientation not in ("horizontal", "vertical"):
            orientation = "horizontal"

        raw_children = data.get("children", [])
        children: list[SplitNodeState] = []
        if isinstance(raw_children, list):
            for c in raw_children:
                if isinstance(c, dict):
                    children.append(cls.from_dict(c))

        raw_pane = data.get("pane")
        pane = PaneState.from_dict(raw_pane) if (is_leaf or raw_pane) else None

        if not is_leaf and not children:
            # Container with no valid children degrades to leaf
            is_leaf = True
            pane = pane or PaneState()

        return cls(
            is_leaf=is_leaf,
            orientation=orientation,
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
    def from_dict(cls, data: Any) -> TabState:
        if not isinstance(data, dict):
            return cls()
        title = data.get("title", "Terminal")
        if not isinstance(title, str):
            title = "Terminal"
        root_data = data.get("root", {})
        return cls(
            title=title,
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
    def from_dict(cls, data: Any) -> SessionState:
        if not isinstance(data, dict):
            return cls(tabs=[TabState()])

        version = data.get("version", 1)
        if not isinstance(version, int):
            version = 1

        active_tab_index = data.get("active_tab_index", 0)
        if not isinstance(active_tab_index, int) or active_tab_index < 0:
            active_tab_index = 0

        raw_tabs = data.get("tabs", [])
        tabs: list[TabState] = []
        if isinstance(raw_tabs, list):
            for t in raw_tabs:
                if isinstance(t, dict):
                    tabs.append(TabState.from_dict(t))

        if not tabs:
            tabs.append(TabState())

        if active_tab_index >= len(tabs):
            active_tab_index = 0

        return cls(
            version=version,
            active_tab_index=active_tab_index,
            tabs=tabs,
        )

    def save(self, path: Path | str | None = None) -> Path:
        """Atomically save session state to JSON file via temporary file and rename."""
        target_path = Path(path) if path is not None else self.default_state_path()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            "w",
            dir=str(target_path.parent),
            delete=False,
            encoding="utf-8",
            prefix=".session_state_",
            suffix=".tmp",
        ) as temp_file:
            temp_name = temp_file.name
            try:
                json.dump(self.to_dict(), temp_file, indent=2)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            except BaseException:
                if os.path.exists(temp_name):
                    try:
                        os.remove(temp_name)
                    except OSError:
                        pass
                raise

        os.replace(temp_name, target_path)
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
            if isinstance(data, dict):
                return cls.from_dict(data)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None
