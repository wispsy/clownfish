"""Keyboard encoding routines including standard xterm sequences and Kitty keyboard protocol."""

from __future__ import annotations

import sys


def _get_modifier_mask(keysym: str, state: int) -> int:
    """Calculate xterm/Kitty modifier code (1 + Shift=1, Alt=2, Ctrl=4, Super=8).

    Correctly filters hardware flags (such as 0x40 on macOS for navigation/Fn keys
    and 0x10 on Linux for NumLock) so arrow keys are not corrupted with spurious modifiers.
    """
    is_mac = sys.platform == "darwin"
    mod = 1
    if state & 0x1:  # Shift
        mod += 1

    # Alt / Option (Meta):
    # - 0x8: standard Mod1 (Alt / Option across xterm/Kitty and X11)
    # - 0x10: on macOS Aqua Tk, Option is Mod2 (0x10)
    # - 0x80: Mod5 / AltGr
    if (state & 0x8) or (state & 0x80) or (is_mac and (state & 0x10)):
        mod += 2

    if state & 0x4:  # Control
        mod += 4

    # Super (Windows / Command key):
    # On Linux/X11, Mod4 (0x40) is Super.
    # On macOS, 0x40 is the hardware Fn/Arrow key flag (NSEventModifierFlagFunction)
    # and must never be treated as Super.
    if not is_mac and (state & 0x40):
        mod += 8

    return mod


def encode_kitty_key(keysym: str, state: int, char: str = "") -> bytes | None:
    """Encode key event into Kitty/xterm modified keyboard escape sequences."""
    mod = _get_modifier_mask(keysym, state)

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
        "F1": f"\x1b[1;{mod}P".encode("ascii"),
        "F2": f"\x1b[1;{mod}Q".encode("ascii"),
        "F3": f"\x1b[1;{mod}R".encode("ascii"),
        "F4": f"\x1b[1;{mod}S".encode("ascii"),
        "F5": f"\x1b[15;{mod}~".encode("ascii"),
        "F6": f"\x1b[17;{mod}~".encode("ascii"),
        "F7": f"\x1b[18;{mod}~".encode("ascii"),
        "F8": f"\x1b[19;{mod}~".encode("ascii"),
        "F9": f"\x1b[20;{mod}~".encode("ascii"),
        "F10": f"\x1b[21;{mod}~".encode("ascii"),
        "F11": f"\x1b[23;{mod}~".encode("ascii"),
        "F12": f"\x1b[24;{mod}~".encode("ascii"),
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
    # 1. Kitty keyboard protocol for modified keys
    if kitty_keyboard_flags & 1:
        kitty_encoded = encode_kitty_key(keysym, state, char)
        if kitty_encoded is not None:
            return kitty_encoded

    mod = _get_modifier_mask(keysym, state)

    # 2. Shift+Tab in xterm
    if keysym == "ISO_Left_Tab" or (keysym == "Tab" and (state & 0x1)):
        return b"\x1b[Z"

    # 3. Standard xterm modified navigation and function keys
    if mod > 1:
        modified_keys = {
            "Up": f"\x1b[1;{mod}A".encode("ascii"),
            "Down": f"\x1b[1;{mod}B".encode("ascii"),
            "Right": f"\x1b[1;{mod}C".encode("ascii"),
            "Left": f"\x1b[1;{mod}D".encode("ascii"),
            "Home": f"\x1b[1;{mod}H".encode("ascii"),
            "End": f"\x1b[1;{mod}F".encode("ascii"),
            "Insert": f"\x1b[2;{mod}~".encode("ascii"),
            "Delete": f"\x1b[3;{mod}~".encode("ascii"),
            "Prior": f"\x1b[5;{mod}~".encode("ascii"),
            "Next": f"\x1b[6;{mod}~".encode("ascii"),
            "F1": f"\x1b[1;{mod}P".encode("ascii"),
            "F2": f"\x1b[1;{mod}Q".encode("ascii"),
            "F3": f"\x1b[1;{mod}R".encode("ascii"),
            "F4": f"\x1b[1;{mod}S".encode("ascii"),
            "F5": f"\x1b[15;{mod}~".encode("ascii"),
            "F6": f"\x1b[17;{mod}~".encode("ascii"),
            "F7": f"\x1b[18;{mod}~".encode("ascii"),
            "F8": f"\x1b[19;{mod}~".encode("ascii"),
            "F9": f"\x1b[20;{mod}~".encode("ascii"),
            "F10": f"\x1b[21;{mod}~".encode("ascii"),
            "F11": f"\x1b[23;{mod}~".encode("ascii"),
            "F12": f"\x1b[24;{mod}~".encode("ascii"),
        }
        if keysym in modified_keys:
            return modified_keys[keysym]

    arrow_prefix = b"\x1bO" if application_cursor_keys else b"\x1b["

    arrow_map = {
        "Up": arrow_prefix + b"A",
        "Down": arrow_prefix + b"B",
        "Right": arrow_prefix + b"C",
        "Left": arrow_prefix + b"D",
        "Home": arrow_prefix + b"H",
        "End": arrow_prefix + b"F",
    }

    f_keys_unmodified = {
        "F1": b"\x1bOP",
        "F2": b"\x1bOQ",
        "F3": b"\x1bOR",
        "F4": b"\x1bOS",
        "F5": b"\x1b[15~",
        "F6": b"\x1b[17~",
        "F7": b"\x1b[18~",
        "F8": b"\x1b[19~",
        "F9": b"\x1b[20~",
        "F10": b"\x1b[21~",
        "F11": b"\x1b[23~",
        "F12": b"\x1b[24~",
    }
    if keysym in f_keys_unmodified:
        return f_keys_unmodified[keysym]

    keymap = {
        "Return": b"\r",
        "BackSpace": b"\x7f",
        "Tab": b"\t",
        "Escape": b"\x1b",
        "Insert": b"\x1b[2~",
        "Delete": b"\x1b[3~",
        "Prior": b"\x1b[5~",
        "Next": b"\x1b[6~",
    }

    if keysym in arrow_map:
        return arrow_map[keysym]
    if keysym in keymap:
        return keymap[keysym]
    is_mac = sys.platform == "darwin"
    has_alt = bool((state & 0x10) if is_mac else (state & 0x8 or state & 0x80))
    if (state & 0x4) and keysym.isalpha() and len(keysym) == 1:
        return bytes([ord(keysym.lower()) - 96])
    if has_alt and char and not (state & 0x4):
        return b"\x1b" + char.encode("utf-8")
    if char:
        return char.encode("utf-8")

    return None
