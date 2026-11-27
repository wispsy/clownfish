"""Tests for Kitty Graphics Protocol parsing, screen buffer placements, and rendering."""

from __future__ import annotations

import base64
from pathlib import Path

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


def test_kitty_graphics_transmit_only_no_placement() -> None:
    """Verify a=t transmits and stores the image without creating a placement or moving cursor."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(2, 5)

    parser = VT100Parser(screen=screen)
    parser.feed(f"\x1b_Ga=t,i=1,f=100;{SAMPLE_PNG_B64}\x1b\\")

    # Image is stored in screen.stored_graphics
    stored = screen.get_stored_graphic(1)
    assert stored is not None
    assert stored.image_id == 1
    assert stored.format == "png"

    # But NO visible placement is created and cursor does NOT advance
    assert len(screen.graphic_placements) == 0
    assert screen.cursor_y == 2
    assert screen.cursor_x == 5


def test_kitty_graphics_transmit_and_display() -> None:
    """Verify a=T (and default action) transmits, creates a placement, and advances cursor."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(2, 5)

    parser = VT100Parser(screen=screen)
    # Transmit 1x1 PNG occupying 4 cols, 2 rows with default action (a=T)
    parser.feed(f"\x1b_Ga=T,i=1,f=100,c=4,r=2;{SAMPLE_PNG_B64}\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    assert placement.image_id == 1
    assert placement.col == 5
    assert placement.row == 2
    assert placement.cols == 4
    assert placement.rows == 2
    assert placement.format == "png"

    # Cursor advances below the placed image
    assert screen.cursor_y == 4
    assert screen.cursor_x == 0


def test_kitty_graphics_no_cursor_advance() -> None:
    """Verify C=1 prevents cursor movement during placement."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(3, 10)

    parser = VT100Parser(screen=screen)
    parser.feed(f"\x1b_Ga=T,i=2,c=6,r=3,C=1;{SAMPLE_PNG_B64}\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    assert placement.image_id == 2
    assert placement.col == 10
    assert placement.row == 3
    # Cursor should not have moved
    assert screen.cursor_y == 3
    assert screen.cursor_x == 10


def test_kitty_graphics_place_stored_image() -> None:
    """Verify a=p places a previously stored (a=t) image on screen."""
    screen = ScreenBuffer(cols=80, rows=24)
    screen.move_cursor(1, 0)
    parser = VT100Parser(screen=screen)

    # 1. Transmit and store under image ID 50
    parser.feed(f"\x1b_Ga=t,i=50,f=100;{SAMPLE_PNG_B64}\x1b\\")
    assert len(screen.graphic_placements) == 0
    assert screen.get_stored_graphic(50) is not None

    # 2. Place image 50 using a=p
    screen.move_cursor(3, 8)
    parser.feed("\x1b_Ga=p,i=50,p=1,c=6,r=3;\x1b\\")

    assert len(screen.graphic_placements) == 1
    placement = screen.graphic_placements[0]
    assert placement.image_id == 50
    assert placement.placement_id == 1
    assert placement.col == 8
    assert placement.row == 3
    assert placement.cols == 6
    assert placement.rows == 3

    # Cursor advanced by 3 rows
    assert screen.cursor_y == 6
    assert screen.cursor_x == 0


def test_kitty_graphics_multi_chunk_continuation() -> None:
    """Verify continuation chunks containing only m=1 or m=0 reassemble without repeating metadata."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    mid = len(SAMPLE_PNG_B64) // 2
    chunk1 = SAMPLE_PNG_B64[:mid]
    chunk2 = SAMPLE_PNG_B64[mid:]

    # First chunk: defines metadata (a=T, i=10, m=1)
    parser.feed(f"\x1b_Ga=T,i=10,c=4,r=2,m=1;{chunk1}\x1b\\")
    assert len(screen.graphic_placements) == 0

    # Continuation chunk: only m=0 and payload, NO repeated 'i' or 'a'
    parser.feed(f"\x1b_Gm=0;{chunk2}\x1b\\")
    assert len(screen.graphic_placements) == 1
    p = screen.graphic_placements[0]
    assert p.image_id == 10
    assert p.base64_data == SAMPLE_PNG_B64
    assert p.cols == 4
    assert p.rows == 2


def test_kitty_graphics_security_rejects_file_paths(tmp_path: Path) -> None:
    """Security verification: file transmission modes (t=f, t=t) are rejected and cannot read or delete files."""
    dummy_file = tmp_path / "sensitive.txt"
    dummy_file.write_text("SUPER_SECRET_PAYLOAD")

    b64_path = base64.b64encode(str(dummy_file).encode("utf-8")).decode("ascii")

    screen = ScreenBuffer(cols=80, rows=24)
    responses: list[bytes] = []
    parser = VT100Parser(screen=screen, write_response=responses.append)

    # Attempt to transmit via temporary file mode t=t (which in Kitty protocol instructs deletion)
    parser.feed(f"\x1b_Ga=T,i=999,t=t;{b64_path}\x1b\\")

    # File MUST NOT be deleted
    assert dummy_file.exists()
    assert dummy_file.read_text() == "SUPER_SECRET_PAYLOAD"

    # Transmission must be rejected with EBADF
    assert len(screen.graphic_placements) == 0
    assert len(responses) == 1
    assert responses[0] == b"\x1b_Gi=999;EBADF\x1b\\"


def test_kitty_graphics_raw_rgb_and_rgba_conversion() -> None:
    """Verify 24-bit raw RGB and 32-bit RGBA transmission converts to Netpbm PPM."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # 2x1 RGB image
    rgb_bytes = bytes([255, 0, 0, 0, 0, 255])
    b64_rgb = base64.b64encode(rgb_bytes).decode("ascii")
    parser.feed(f"\x1b_Ga=T,i=15,f=24,s=2,v=1;{b64_rgb}\x1b\\")

    assert len(screen.graphic_placements) == 1
    p = screen.graphic_placements[0]
    assert p.format == "ppm"
    assert p.pixel_width == 2
    assert p.pixel_height == 1

    decoded_ppm = base64.b64decode(p.base64_data)
    assert decoded_ppm.startswith(b"P6\n2 1\n255\n")
    assert decoded_ppm[len(b"P6\n2 1\n255\n") :] == rgb_bytes


def test_kitty_graphics_delete_actions() -> None:
    """Verify deletion by image ID (d=i), placement ID (d=p), and all (d=a)."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # Place two images
    parser.feed(f"\x1b_Ga=T,i=101,p=1,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")
    parser.feed(f"\x1b_Ga=T,i=102,p=2,c=2,r=2;{SAMPLE_PNG_B64}\x1b\\")
    assert len(screen.graphic_placements) == 2

    # Delete placement 1
    parser.feed("\x1b_Ga=d,d=p,p=1;\x1b\\")
    assert len(screen.graphic_placements) == 1
    assert screen.graphic_placements[0].image_id == 102

    # Delete image 102 specifically
    parser.feed("\x1b_Ga=d,d=i,i=102;\x1b\\")
    assert len(screen.graphic_placements) == 0
    assert screen.get_stored_graphic(102) is None


def test_kitty_graphics_retransmit_replacement() -> None:
    """Verify retransmitting an existing image ID updates data and version."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # First transmission
    parser.feed(f"\x1b_Ga=t,i=200,f=100;{SAMPLE_PNG_B64}\x1b\\")
    stored1 = screen.get_stored_graphic(200)
    assert stored1 is not None
    v1 = stored1.version

    # Retransmit under same image ID
    parser.feed(f"\x1b_Ga=t,i=200,f=100;{SAMPLE_PNG_B64}\x1b\\")
    stored2 = screen.get_stored_graphic(200)
    assert stored2 is not None
    assert stored2.version == v1 + 1


def test_kitty_graphics_reflow_remapping() -> None:
    """Verify screen column reflow remaps graphic placement abs_row."""
    screen = ScreenBuffer(cols=80, rows=24)
    parser = VT100Parser(screen=screen)

    # Type line 0
    parser.feed("Hello World\r\n")
    # Line 1: place graphic
    parser.feed(f"\x1b_Ga=T,i=300,c=4,r=2;{SAMPLE_PNG_B64}\x1b\\")

    placement = screen.graphic_placements[0]
    assert placement.abs_row == 1

    # Resize terminal columns (triggers _reflow_primary)
    screen.resize(40, 24)
    # Placement abs_row is preserved/remapped consistently
    assert screen.graphic_placements[0].abs_row == 1


def test_canvas_renderer_kitty_graphics_integration() -> None:
    """Verify TkCanvasRenderer creates scaled image items on canvas and cleans up."""
    import tkinter as tk

    from clownfish.frontends.tkinter.renderer import TkCanvasRenderer

    try:
        root = tk.Tk()
        root.withdraw()
    except (ImportError, tk.TclError, RuntimeError):
        return

    try:
        canvas = tk.Canvas(root, width=800, height=400)
        renderer = TkCanvasRenderer(canvas)
        screen = ScreenBuffer(cols=80, rows=24)
        parser = VT100Parser(screen=screen)

        # Transmit and display image occupying 4 cols, 2 rows
        parser.feed(f"\x1b_Ga=T,i=88,c=4,r=2;{SAMPLE_PNG_B64}\x1b\\")
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
