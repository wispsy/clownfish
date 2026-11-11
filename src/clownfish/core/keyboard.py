"""Keyboard encoding routines including standard xterm sequences and Kitty keyboard protocol."""

from __future__ import annotations


def encode_kitty_key(keysym: str, state: int, char: str = "") -> bytes | None:
    """Encode key event into Kitty/xterm modified keyboard escape sequences."""
    # Modifiers: Shift=1, Alt=2, Ctrl=4, Super=8. Parameter value = 1 + bitmask.
    mod = 1
    if state & 0x1:  # Shift
        mod += 1
    if state & 0x8 or state & 0x80:  # Alt / Option (Meta)
        mod += 2
    if state & 0x4:  # Control
        mod += 4
    if state & 0x40 or state & 0x10:  # Super / Command
        mod += 8

    if mod <= 1:
        return None

    # Standard xterm/Kitty modified navigation and cursor keys:
    # Arrow keys use CSI 1;modifier [A-D]
    # Home/End use CSI 1;modifier [H,F]
    # PC edit keys use CSI <key-id>;modifier ~
    nav_keys = {
        "Up": f"\x1b[1;{mod}A".encode("ascii"),
        "Down": f"\x1b[1;{mod}B".encode("ascii"),
        "Right": f"\x1b[1;{mod}C".encode("ascii"),
        "Left": f"\x1b[1;{mod}D".encode("ascii"),
        "Home": f"\x1b[1;{mod}H".encode("ascii"),
        "End": f"\x1b[1;{mod}F".encode("ascii"),
        "Insert": f"\x1b[2;{mod}~".encode("ascii"),
        "Delete": f"\x1b[3;{mod}~".encode("ascii"),
        "Prior": f"\x1b[5;{mod}~".encode("ascii"),  # Page Up
        "Next": f"\x1b[6;{mod}~".encode("ascii"),   # Page Down
    }
    if keysym in nav_keys:
        return nav_keys[keysym]

    # Functional keys with Kitty CSI u encoding:
    kitty_u_keys = {
        "Return": 13,
        "Tab": 9,
        "BackSpace": 127,
        "Escape": 27,
    }
    if keysym in kitty_u_keys:
        code = kitty_u_keys[keysym]
        return f"\x1b[{code};{mod}u".encode("ascii")

    # Regular character keys with modifier (e.g. Ctrl+C -> 99;5u)
    if len(char) == 1:
        code = ord(char.lower() if (mod & 4) else char)
        return f"\x1b[{code};{mod}u".encode("ascii")

    return None


def encode_key_press(
    keysym: str,
    state: int = 0,
    char: str = "",
    kitty_keyboard_flags: int = 0,
    application_cursor_keys: bool = False,
) -> bytes | None:
    """Encode a keyboard event into terminal bytes."""
    # Kitty keyboard protocol for modified keys
    if kitty_keyboard_flags & 1:
        kitty_encoded = encode_kitty_key(keysym, state, char)
        if kitty_encoded is not None:
            return kitty_encoded

    arrow_prefix = b"\x1bO" if application_cursor_keys else b"\x1b["

    arrow_map = {
        "Up": arrow_prefix + b"A",
        "Down": arrow_prefix + b"B",
        "Right": arrow_prefix + b"C",
        "Left": arrow_prefix + b"D",
        "Home": arrow_prefix + b"H",
        "End": arrow_prefix + b"F",
    }

    keymap = {
        "Return": b"\r",
        "BackSpace": b"\x7f",
        "Tab": b"\t",
        "Escape": b"\x1b",
        "Delete": b"\x1b[3~",
        "Prior": b"\x1b[5~",
        "Next": b"\x1b[6~",
    }

    if keysym in arrow_map:
        return arrow_map[keysym]
    if keysym in keymap:
        return keymap[keysym]
    if (state & 0x4) and keysym.isalpha() and len(keysym) == 1:
        return bytes([ord(keysym.lower()) - 96])
    if char:
        return char.encode("utf-8")

    return None
