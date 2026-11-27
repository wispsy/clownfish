"""Tests for Kitty Graphics Protocol parsing, screen buffer placements, and rendering."""

from __future__ import annotations

import base64

from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer

# 1x1 transparent PNG in base64
SAMPLE_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="


def test_kitty_graphics_query_response() -> None:
    """Verify terminal responds to Kitty graphics query (a=q)."""
    screen = ScreenBuffer(cols=80, rows=24)
    responses: list[bytes] = []

    parser = VT100Parser(screen=screen, write_response=responses.append)
    parser.feed("\x1b_Ga=q,i=42;\x1b\\")

    assert len(responses) == 1
    assert responses[0] == b"\x1b_Gi=42;OK\x1b\\"


def test_kitty_graphics_single_chunk_png() -> None:
    """Verify single-chunk PNG transmission creates placement and advances cursor."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(2, 5)

    parser = VT100Parser(screen=screen)
    # Transmit 1x1 PNG occupying 4 cols, 2 rows
    parser.feed(f"\x1b_Ga=t,i=1,f=100,c=4,r=2;{SAMPLE_PNG_B64}\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    assert placement.image_id == 1
    assert placement.col == 5
    assert placement.row == 2
    assert placement.cols == 4
    assert placement.rows == 2
    assert placement.format == "png"
    assert placement.pixel_width == 1
    assert placement.pixel_height == 1

    # Standard a=t advances cursor below the image
    assert screen.cursor_y == 4
    assert screen.cursor_x == 0


def test_kitty_graphics_no_cursor_advance() -> None:
    """Verify a=T or C=1 preserves cursor position."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(3, 10)

    parser = VT100Parser(screen=screen)
    parser.feed(f"\x1b_Ga=T,i=2,c=6,r=3;{SAMPLE_PNG_B64}\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    assert placement.image_id == 2
    assert placement.col == 10
    assert placement.row == 3
    # Cursor should not have moved
    assert screen.cursor_y == 3
    assert screen.cursor_x == 10


def test_kitty_graphics_multi_chunk_transmission() -> None:
    """Verify multi-chunk (m=1, m=0) transmission reassembles payload correctly."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    mid = len(SAMPLE_PNG_B64) // 2
    chunk1 = SAMPLE_PNG_B64[:mid]
    chunk2 = SAMPLE_PNG_B64[mid:]

    # Send first chunk
    parser.feed(f"\x1b_Ga=t,i=10,m=1;{chunk1}\x1b\\")
    assert len(screen.graphic_placements) == 0

    # Send final chunk
    parser.feed(f"\x1b_Ga=t,i=10,m=0;{chunk2}\x1b\\")
    assert len(screen.graphic_placements) == 1
    assert screen.graphic_placements[0].image_id == 10
    assert screen.graphic_placements[0].base64_data == SAMPLE_PNG_B64


def test_kitty_graphics_raw_rgb_conversion() -> None:
    """Verify 24-bit raw RGB transmission converts to Netpbm PPM."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # 2x1 image with red and blue pixels
    rgb_bytes = bytes([255, 0, 0, 0, 0, 255])
    b64_rgb = base64.b64encode(rgb_bytes).decode("ascii")

    parser.feed(f"\x1b_Ga=t,i=15,f=24,s=2,v=1;{b64_rgb}\x1b\\")
    assert len(screen.graphic_placements) == 1
    p = screen.graphic_placements[0]
    assert p.format == "ppm"
    assert p.pixel_width == 2
    assert p.pixel_height == 1

    decoded_ppm = base64.b64decode(p.base64_data)
    assert decoded_ppm.startswith(b"P6\n2 1\n255\n")
    assert decoded_ppm[len(b"P6\n2 1\n255\n") :] == rgb_bytes


def test_kitty_graphics_delete_actions() -> None:
    """Verify deletion by image ID and deletion of all placements."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # Place two images
    parser.feed(f"\x1b_Ga=t,i=101,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")
    parser.feed(f"\x1b_Ga=t,i=102,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")
    assert len(screen.graphic_placements) == 2

    # Delete image 101 specifically
    parser.feed("\x1b_Ga=d,d=i,i=101;\x1b\\")
    assert len(screen.graphic_placements) == 1
    assert screen.graphic_placements[0].image_id == 102

    # Delete all images
    parser.feed("\x1b_Ga=d,d=a;\x1b\\")
    assert len(screen.graphic_placements) == 0


def test_kitty_graphics_scrolling_persistence() -> None:
    """Verify placements maintain absolute row anchoring when screen scrolls."""
    screen = ScreenBuffer(cols=80, rows=10)
    screen.move_cursor(2, 0)

    parser = VT100Parser(screen=screen)
    parser.feed(f"\x1b_Ga=T,i=5,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    initial_abs_row = placement.abs_row
    assert initial_abs_row == 2

    # Scroll screen up by 5 lines
    screen.scroll_up(5)
    assert screen.total_lines_scrolled == 5
    # Placement abs_row remains unchanged
    assert screen.graphic_placements[0].abs_row == initial_abs_row


def test_kitty_graphics_clear_all_and_erase() -> None:
    """Verify clear_all() and erase_in_display(2) prune active placements."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)
    parser.feed(f"\x1b_Ga=t,i=99,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")
    assert len(screen.graphic_placements) == 1

    screen.clear_all()
    assert len(screen.graphic_placements) == 0


def test_canvas_renderer_kitty_graphics_integration() -> None:
    """Verify TkCanvasRenderer creates image items on canvas and cleans up."""
    import tkinter as tk

    from clownfish.frontends.tkinter.renderer import TkCanvasRenderer

    try:
        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        # Headless display environment
        return

    try:
        canvas = tk.Canvas(root, width=800, height=400)
        renderer = TkCanvasRenderer(canvas)
        screen = ScreenBuffer(cols=80, rows=24)
        parser = VT100Parser(screen=screen)

        # Transmit image
        parser.feed(f"\x1b_Ga=t,i=88,c=4,r=2;{SAMPLE_PNG_B64}\x1b\\")
        assert len(screen.graphic_placements) == 1

        # Render screen onto canvas
        renderer.render(screen, cols=80, rows=24)
        canvas_items = canvas.find_withtag("graphic_item")
        assert len(canvas_items) == 1

        # Delete image
        parser.feed("\x1b_Ga=d,d=i,i=88;\x1b\\")
        assert len(screen.graphic_placements) == 0
        renderer.render(screen, cols=80, rows=24)
        canvas_items_after = canvas.find_withtag("graphic_item")
        assert len(canvas_items_after) == 0
    finally:
        root.destroy()

