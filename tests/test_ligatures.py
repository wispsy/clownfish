"""Tests for ligature pattern matching, monospace run segmentation, and configuration."""

from __future__ import annotations

from clownfish.config import TerminalConfig
from clownfish.core.ligatures import find_ligatures, is_ligature, segment_row_cells
from clownfish.core.models import Cell, Row, Style


def test_ligature_pattern_recognition() -> None:
    """Verify standard developer font ligatures are recognized."""
    assert is_ligature("!=")
    assert is_ligature("==")
    assert is_ligature("===")
    assert is_ligature("->")
    assert is_ligature("=>")
    assert is_ligature("<=")
    assert is_ligature(">=")
    assert is_ligature("/*")
    assert is_ligature("::")
    assert not is_ligature("abc")
    assert not is_ligature("!!=")


def test_find_ligatures_in_code_string() -> None:
    """Verify all occurrences and offsets of ligatures are located."""
    text = "const is_valid = (a != b) => a >= 0 && b <= 100;"
    matches = find_ligatures(text)
    ligatures_found = [m[2] for m in matches]
    assert "!=" in ligatures_found
    assert "=>" in ligatures_found
    assert ">=" in ligatures_found
    assert "&&" in ligatures_found
    assert "<=" in ligatures_found


def test_segment_row_cells_with_ligatures_enabled() -> None:
    """Verify segment_row_cells groups identical styles and tags ligatures."""
    # Build row: "x != y"
    cells = [
        Cell(char="x"),
        Cell(char=" "),
        Cell(char="!"),
        Cell(char="="),
        Cell(char=" "),
        Cell(char="y"),
    ]
    # Pad to 10 cols
    cells.extend([Cell(char=" ") for _ in range(4)])
    row = Row(cells)

    segments = segment_row_cells(row, cols=10, enable_ligatures=True)
    # Segments should isolate "!=" as a ligature segment
    lig_segs = [s for s in segments if s.is_ligature]
    assert len(lig_segs) == 1
    assert lig_segs[0].text == "!="
    assert lig_segs[0].start_col == 2
    assert lig_segs[0].end_col == 4
    assert lig_segs[0].width == 2


def test_segment_row_cells_with_ligatures_disabled() -> None:
    """Verify ligatures are not tagged when enable_ligatures is False."""
    cells = [
        Cell(char="x"),
        Cell(char=" "),
        Cell(char="!"),
        Cell(char="="),
        Cell(char=" "),
        Cell(char="y"),
    ]
    row = Row(cells)

    segments = segment_row_cells(row, cols=6, enable_ligatures=False)
    lig_segs = [s for s in segments if s.is_ligature]
    assert len(lig_segs) == 0


def test_segment_row_cells_preserves_style_boundaries() -> None:
    """Verify styled tokens do not leak into different style runs."""
    st1 = Style(bold=True)
    st2 = Style(italic=True)

    cells = [
        Cell(char="!", style=st1),
        Cell(char="=", style=st2),
    ]
    row = Row(cells)

    segments = segment_row_cells(row, cols=2, enable_ligatures=True)
    # Because styles differ, they cannot be merged into a single ligature
    assert len(segments) == 2
    assert not any(s.is_ligature for s in segments)


def test_config_enable_ligatures_setting() -> None:
    """Verify enable_ligatures option in TerminalConfig defaults to False and serializes."""
    cfg = TerminalConfig()
    assert cfg.enable_ligatures is False

    data = cfg.to_dict()
    assert data["enable_ligatures"] is False

    cfg_enabled = TerminalConfig.from_dict({"enable_ligatures": True})
    assert cfg_enabled.enable_ligatures is True


def test_canvas_renderer_ligatures_integration() -> None:
    """Verify TkCanvasRenderer applies ligature tags to canvas text items."""
    import tkinter as tk

    from clownfish.core.parser import VT100Parser
    from clownfish.core.screen import ScreenBuffer
    from clownfish.frontends.tkinter.renderer import TkCanvasRenderer

    try:
        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        return

    try:
        canvas = tk.Canvas(root, width=800, height=400)
        cfg = TerminalConfig(enable_ligatures=True)
        renderer = TkCanvasRenderer(canvas, config=cfg)
        screen = ScreenBuffer(cols=80, rows=24)
        parser = VT100Parser(screen=screen)

        parser.feed("fn = (x) => x != 0\r\n")
        renderer.render(screen, cols=80, rows=24)

        ligature_items = canvas.find_withtag("ligature_item")
        assert len(ligature_items) >= 2  # '=>' and '!='
    finally:
        root.destroy()

