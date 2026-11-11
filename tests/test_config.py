"""Tests for TerminalConfig."""

from __future__ import annotations

from pathlib import Path

from clownfish.config import TerminalConfig


def test_config_defaults() -> None:
    config = TerminalConfig()
    assert config.cols == 80
    assert config.rows == 24
    assert config.max_scrollback == 10_000
    assert config.cursor_color == "#e5e5e5"
    assert config.search_bg == "#d7ba7d"


def test_config_save_and_load(tmp_path: Path) -> None:
    config_file = tmp_path / "custom" / "config.json"
    cfg = TerminalConfig(
        cols=120,
        rows=40,
        font_size=16,
        cursor_color="#ff5555",
        default_fg=(200, 210, 220),
    )

    saved_path = cfg.save(config_file)
    assert saved_path == config_file
    assert config_file.exists()

    loaded_cfg = TerminalConfig.load(config_file)
    assert loaded_cfg.cols == 120
    assert loaded_cfg.rows == 40
    assert loaded_cfg.font_size == 16
    assert loaded_cfg.cursor_color == "#ff5555"
    assert loaded_cfg.default_fg == (200, 210, 220)


def test_config_load_nonexistent_returns_defaults(tmp_path: Path) -> None:
    cfg = TerminalConfig.load(tmp_path / "does_not_exist.json")
    assert cfg.cols == 80
    assert cfg.rows == 24
