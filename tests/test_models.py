"""Unit tests for clownfish models."""

from clownfish.models import Cell, Selection, Style


def test_style_defaults_and_copy():
    s = Style()
    assert s.bold is False
    assert s.italic is False
    assert s.underline is False
    assert s.reverse is False

    s_copied = s.copy()
    s_copied.bold = True
    assert s.bold is False
    assert s_copied.bold is True


def test_cell_defaults():
    c = Cell()
    assert c.char == " "
    assert c.style.bold is False
    assert c.url is None


def test_selection_normalization_and_empty():
    sel = Selection()
    assert sel.is_empty()

    sel.active = True
    sel.start_col, sel.start_row = 5, 2
    sel.end_col, sel.end_row = 5, 2
    assert sel.is_empty()

    sel.end_col, sel.end_row = 10, 2
    assert not sel.is_empty()
    p1, p2 = sel.normalized()
    assert p1 == (5, 2)
    assert p2 == (10, 2)

    # Reverse selection
    sel.start_col, sel.start_row = 12, 4
    sel.end_col, sel.end_row = 2, 1
    p1, p2 = sel.normalized()
    assert p1 == (2, 1)
    assert p2 == (12, 4)


def test_clownfish_module_attributes():
    import pytest

    import clownfish

    with pytest.raises(AttributeError):
        _ = clownfish.non_existent_attribute

    try:
        import _tkinter  # noqa: F401

        from clownfish.app import TkTerminalApp

        assert clownfish.TkTerminalApp is TkTerminalApp
    except (ImportError, ModuleNotFoundError):
        with pytest.raises((ImportError, ModuleNotFoundError)):
            _ = clownfish.TkTerminalApp


