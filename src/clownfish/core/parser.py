"""VT100, ANSI, and OSC escape sequence parser."""

import base64
import binascii
import os
import socket
import struct
import urllib.parse
from collections.abc import Callable

from clownfish.core.models import DEFAULT_BG, DEFAULT_FG, GraphicImage, GraphicPlacement
from clownfish.core.screen import ScreenBuffer


class VT100Parser:
    """State machine parser decoding ANSI/VT100/OSC control streams."""

    STATE_GROUND = 0
    STATE_ESCAPE = 1
    STATE_CSI = 2
    STATE_OSC = 3
    STATE_STRING = 4  # DCS, APC, PM, SOS

    MAX_OSC_LENGTH: int = 8192
    MAX_STRING_LENGTH: int = 8192
    MAX_GRAPHIC_STRING_LENGTH: int = 10_485_760  # 10 MB for Kitty Graphics payloads
    MAX_IMAGE_BYTES: int = 10 * 1024 * 1024  # 10 MB max decoded image size
    MAX_IMAGE_WIDTH: int = 4096
    MAX_IMAGE_HEIGHT: int = 4096
    MAX_PARAM_DIGITS: int = 32
    MAX_PARAMS: int = 64
    MAX_SUBPARAMS: int = 16

    def __init__(
        self,
        screen: ScreenBuffer,
        write_response: Callable[[bytes], None] | None = None,
        on_title_change: Callable[[str], None] | None = None,
        on_cwd_change: Callable[[str], None] | None = None,
        on_notification: Callable[[str, str], None] | None = None,
        on_clipboard_write: Callable[[str, str], None] | None = None,
        on_clipboard_query: Callable[[str], str] | None = None,
        on_bell: Callable[[], None] | None = None,
    ):
        self.screen = screen
        self.write_response = write_response
        self.on_title_change = on_title_change
        self.on_cwd_change = on_cwd_change
        self.on_notification = on_notification
        self.on_clipboard_write = on_clipboard_write
        self.on_clipboard_query = on_clipboard_query
        self.on_bell = on_bell
        self.state = self.STATE_GROUND
        self.params: list[list[int]] = []
        self.current_subparams: list[int] = []
        self.current_param = ""
        self.private_mode = False
        self.secondary_da = False
        self.csi_prefix = ""
        self.intermediate_bytes = ""
        self.osc_payload = ""
        self.string_payload = ""
        self.string_type = ""
        self.escape_in_string = False
        self._kitty_active_metadata: dict[str, str] | None = None
        self._kitty_active_chunks: list[str] = []
        self._kitty_active_bytes: int = 0
        self._next_image_id: int = 1000
        self._next_placement_id: int = 1000

        # Terminal Flags
        self.application_cursor_keys = False
        self.bracketed_paste_mode = False
        self.mouse_tracking = False       # ?1000h (Normal tracking)
        self.mouse_button_motion = False  # ?1002h (Button-event motion tracking)
        self.mouse_all_motion = False     # ?1003h (All-event motion tracking)
        self.sgr_mouse_mode = False       # ?1006h (SGR decimal format)
        self.kitty_keyboard_flags = 0
        self.kitty_keyboard_stack: list[int] = []
        self.focus_reporting = False

    def feed(self, text: str):
        i = 0
        n = len(text)
        while i < n:
            if self.state == self.STATE_STRING:
                limit = self.MAX_GRAPHIC_STRING_LENGTH if self.string_type == "_" else self.MAX_STRING_LENGTH
                if self.escape_in_string:
                    char = text[i]
                    i += 1
                    self._handle_string(char)
                    continue

                idx_esc = text.find("\x1b", i)
                idx_bel = text.find("\x07", i)
                idx_st = text.find("\x9c", i)
                candidates = [c for c in (idx_esc, idx_bel, idx_st) if c != -1]
                if candidates:
                    next_delim = min(candidates)
                    chunk = text[i:next_delim]
                    if chunk:
                        avail = max(0, limit - len(self.string_payload))
                        if avail > 0:
                            self.string_payload += chunk[:avail]
                    i = next_delim
                    char = text[i]
                    i += 1
                    self._handle_string(char)
                else:
                    chunk = text[i:]
                    avail = max(0, limit - len(self.string_payload))
                    if avail > 0:
                        self.string_payload += chunk[:avail]
                    break
            else:
                char = text[i]
                i += 1
                if self.state == self.STATE_GROUND:
                    self._handle_ground(char)
                elif self.state == self.STATE_ESCAPE:
                    self._handle_escape(char)
                elif self.state == self.STATE_CSI:
                    self._handle_csi(char)
                elif self.state == self.STATE_OSC:
                    self._handle_osc(char)

    def _handle_ground(self, char: str):
        if char == "\x1b":
            self.state = self.STATE_ESCAPE
        elif char == "\x07":
            if self.on_bell:
                self.on_bell()
        elif char == "\r":
            self.screen.cursor_x = 0
            self.screen.wrap_pending = False
        elif char in ("\n", "\x0b", "\x0c"):
            self.screen.cursor_y += 1
            self.screen.wrap_pending = False
            if self.screen.cursor_y > self.screen.scroll_bottom:
                self.screen.scroll_up(1)
                self.screen.cursor_y = self.screen.scroll_bottom
        elif char == "\b":
            self.screen.cursor_x = max(0, self.screen.cursor_x - 1)
            self.screen.wrap_pending = False
        elif char == "\t":
            self.screen.cursor_x = min(self.screen.cols - 1, (self.screen.cursor_x + 8) & ~7)
            self.screen.wrap_pending = False
        elif ord(char) >= 32:
            self.screen.put_char(char)

    def _handle_escape(self, char: str):
        if char == "[":
            self.state = self.STATE_CSI
            self.params = []
            self.current_subparams = []
            self.current_param = ""
            self.private_mode = False
            self.secondary_da = False
            self.csi_prefix = ""
            self.intermediate_bytes = ""
        elif char == "]":
            self.state = self.STATE_OSC
            self.osc_payload = ""
            self.escape_in_string = False
        elif char in ("P", "_", "^", "X"):
            self.state = self.STATE_STRING
            self.string_type = char
            self.string_payload = ""
            self.escape_in_string = False
        elif char == "7":
            self.screen.save_cursor()
            self.state = self.STATE_GROUND
        elif char == "8":
            self.screen.restore_cursor()
            self.state = self.STATE_GROUND
        elif char == "M":
            self.screen.wrap_pending = False
            if self.screen.cursor_y == self.screen.scroll_top:
                self.screen.scroll_down(1)
            else:
                self.screen.cursor_y = max(0, self.screen.cursor_y - 1)
            self.state = self.STATE_GROUND
        elif char == "c":
            self.screen.erase_in_display(2)
            self.screen.move_cursor(0, 0)
            self.state = self.STATE_GROUND
        else:
            self.state = self.STATE_GROUND

    def _handle_string(self, char: str):
        limit = self.MAX_GRAPHIC_STRING_LENGTH if self.string_type == "_" else self.MAX_STRING_LENGTH
        if char in ("\x07", "\x9c"):
            self.state = self.STATE_GROUND
            self.escape_in_string = False
            self._dispatch_string()
        elif self.escape_in_string:
            self.escape_in_string = False
            if char == "\\":
                self.state = self.STATE_GROUND
                self._dispatch_string()
            elif char == "\x1b":
                self.escape_in_string = True
            elif len(self.string_payload) < limit:
                self.string_payload += "\x1b" + char
        elif char == "\x1b":
            self.escape_in_string = True
        else:
            if len(self.string_payload) < limit:
                self.string_payload += char

    def _dispatch_string(self):
        """Dispatch terminated DCS / APC / PM / SOS strings."""
        if self.string_type == "_" and self.string_payload.startswith("G"):
            self._handle_kitty_graphics(self.string_payload[1:])
        self.string_payload = ""
        self.string_type = ""

    def _handle_kitty_graphics(self, payload: str) -> None:
        """Decode and execute Kitty Graphics Protocol commands (APC G ... ST)."""
        if ";" in payload:
            control_str, data_b64 = payload.split(";", 1)
        else:
            control_str, data_b64 = payload, ""

        params: dict[str, str] = {}
        if control_str:
            for item in control_str.split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    params[k.strip()] = v.strip()

        action = params.get("a", "T")
        quiet = int(params.get("q", "0")) if params.get("q", "").isdigit() else 0
        img_id = int(params.get("i", "0")) if params.get("i", "").isdigit() else 0
        placement_id = int(params.get("p", "0")) if params.get("p", "").isdigit() else 0

        # Security constraint: only direct inline base64 transmission ('t=d' or omitted) is permitted.
        # File paths ('t=f', 't=t') and shared memory ('t=s') are strictly rejected.
        transmission_medium = params.get("t", "d")
        if transmission_medium != "d":
            if self.write_response and quiet == 0:
                self.write_response(f"\x1b_Gi={img_id};EBADF\x1b\\".encode("ascii"))
            return

        # Query action: response with OK
        if action == "q":
            if self.write_response and quiet != 2:
                resp = f"\x1b_Gi={img_id};OK\x1b\\".encode("ascii")
                self.write_response(resp)
            return

        # Delete action
        if action == "d":
            delete_target = params.get("d", "a")
            if delete_target == "a":
                self.screen.delete_graphic_placements("all")
            elif delete_target in ("i", "I"):
                self.screen.delete_graphic_placements("image", image_id=img_id)
            elif delete_target == "p":
                self.screen.delete_graphic_placements("placement", image_id=img_id, placement_id=placement_id)
            if self.write_response and quiet == 0:
                self.write_response(b"\x1b_G;OK\x1b\\")
            return

        # Placement action for already stored image ('a=p')
        if action == "p":
            stored = self.screen.get_stored_graphic(img_id)
            if not stored:
                if self.write_response and quiet == 0:
                    self.write_response(f"\x1b_Gi={img_id};ENOENT\x1b\\".encode("ascii"))
                return

            c_param = int(params.get("c", "0")) if params.get("c", "").isdigit() else 0
            r_param = int(params.get("r", "0")) if params.get("r", "").isdigit() else 0
            cell_w_est = 9
            cell_h_est = 18

            if c_param > 0 and r_param > 0:
                cols = min(self.screen.cols, c_param)
                rows = r_param
            elif c_param > 0:
                cols = min(self.screen.cols, c_param)
                if stored.pixel_width > 0 and stored.pixel_height > 0:
                    target_w = cols * cell_w_est
                    target_h = target_w * (stored.pixel_height / stored.pixel_width)
                    rows = max(1, round(target_h / cell_h_est))
                else:
                    rows = 5
            elif r_param > 0:
                rows = r_param
                if stored.pixel_width > 0 and stored.pixel_height > 0:
                    target_h = rows * cell_h_est
                    target_w = target_h * (stored.pixel_width / stored.pixel_height)
                    cols = min(self.screen.cols, max(1, round(target_w / cell_w_est)))
                else:
                    cols = min(self.screen.cols, 10)
            else:
                cols = min(self.screen.cols, max(1, (stored.pixel_width + cell_w_est - 1) // cell_w_est) if stored.pixel_width > 0 else 10)
                rows = max(1, (stored.pixel_height + cell_h_est - 1) // cell_h_est) if stored.pixel_height > 0 else 5

            cursor_advance = (params.get("C", "0") != "1")
            if placement_id == 0:
                self._next_placement_id += 1
                placement_id = self._next_placement_id

            placement = GraphicPlacement(
                image_id=img_id,
                placement_id=placement_id,
                col=self.screen.cursor_x,
                row=self.screen.cursor_y,
                abs_row=self.screen.total_lines_scrolled + self.screen.cursor_y,
                cols=cols,
                rows=rows,
                cursor_advance=cursor_advance,
            )
            self.screen.add_graphic_placement(placement)

            if cursor_advance:
                for _ in range(rows):
                    self.screen.cursor_y += 1
                    if self.screen.cursor_y > self.screen.scroll_bottom:
                        self.screen.scroll_up(1)
                        self.screen.cursor_y = self.screen.scroll_bottom
                self.screen.cursor_x = 0
                self.screen.wrap_pending = False

            if self.write_response and quiet == 0:
                self.write_response(f"\x1b_Gi={img_id};OK\x1b\\".encode("ascii"))
            return

        # Transmission actions ('t' - transmit only, 'T' - transmit and display)
        more_chunks = (params.get("m", "0") == "1")
        clean_chunk = "".join(data_b64.split()) if data_b64 else ""

        is_continuation = False
        if self._kitty_active_metadata is not None:
            active_id = int(self._kitty_active_metadata.get("i", "0"))
            if img_id == 0 or img_id == active_id:
                is_continuation = True

        if is_continuation:
            self._kitty_active_chunks.append(clean_chunk)
            self._kitty_active_bytes += len(clean_chunk)
            for k, v in params.items():
                if k != "m":
                    self._kitty_active_metadata[k] = v

            if self._kitty_active_bytes > self.MAX_IMAGE_BYTES:
                self._kitty_active_metadata = None
                self._kitty_active_chunks.clear()
                self._kitty_active_bytes = 0
                if self.write_response and quiet == 0:
                    self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
                return

            if more_chunks:
                return

            full_b64 = "".join(self._kitty_active_chunks)
            params = self._kitty_active_metadata
            self._kitty_active_metadata = None
            self._kitty_active_chunks = []
            self._kitty_active_bytes = 0
            action = params.get("a", "T")
            quiet = int(params.get("q", "0")) if params.get("q", "").isdigit() else 0
            img_id = int(params.get("i", "0")) if params.get("i", "").isdigit() else 0
            placement_id = int(params.get("p", "0")) if params.get("p", "").isdigit() else 0
        elif more_chunks:
            self._kitty_active_metadata = params
            self._kitty_active_chunks = [clean_chunk]
            self._kitty_active_bytes = len(clean_chunk)
            return
        else:
            full_b64 = clean_chunk

        try:
            raw_bytes = base64.b64decode(full_b64)
        except (binascii.Error, ValueError):
            if self.write_response and quiet == 0:
                self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
            return

        if not raw_bytes or len(raw_bytes) > self.MAX_IMAGE_BYTES:
            if self.write_response and quiet == 0:
                self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
            return

        if img_id == 0:
            self._next_image_id += 1
            img_id = self._next_image_id

        fmt_code = int(params.get("f", "100")) if params.get("f", "").isdigit() else 100
        pixel_w = int(params.get("s", "0")) if params.get("s", "").isdigit() else 0
        pixel_h = int(params.get("v", "0")) if params.get("v", "").isdigit() else 0
        img_format = "png"
        clean_b64 = ""

        if fmt_code == 100 or raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            img_format = "png"
            if len(raw_bytes) >= 24 and raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                try:
                    pw, ph = struct.unpack(">II", raw_bytes[16:24])
                    if pixel_w == 0:
                        pixel_w = pw
                    if pixel_h == 0:
                        pixel_h = ph
                except struct.error:
                    pass
            if pixel_w > self.MAX_IMAGE_WIDTH or pixel_h > self.MAX_IMAGE_HEIGHT:
                if self.write_response and quiet == 0:
                    self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
                return
            clean_b64 = base64.b64encode(raw_bytes).decode("ascii")
        elif fmt_code in (24, 32) and pixel_w > 0 and pixel_h > 0:
            if pixel_w > self.MAX_IMAGE_WIDTH or pixel_h > self.MAX_IMAGE_HEIGHT:
                if self.write_response and quiet == 0:
                    self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
                return
            expected_len = pixel_w * pixel_h * (3 if fmt_code == 24 else 4)
            if len(raw_bytes) < expected_len:
                if self.write_response and quiet == 0:
                    self.write_response(f"\x1b_Gi={img_id};EINVAL\x1b\\".encode("ascii"))
                return
            img_format = "ppm"
            if fmt_code == 24:
                ppm_header = f"P6\n{pixel_w} {pixel_h}\n255\n".encode("ascii")
                ppm_data = ppm_header + raw_bytes[:expected_len]
                clean_b64 = base64.b64encode(ppm_data).decode("ascii")
            else:
                rgb_buf = bytearray()
                br, bg, bb = DEFAULT_BG
                for idx in range(0, expected_len, 4):
                    r, g, b, a = raw_bytes[idx : idx + 4]
                    if a == 255:
                        rgb_buf.extend((r, g, b))
                    else:
                        alpha = a / 255.0
                        rgb_buf.append(int(r * alpha + br * (1.0 - alpha)))
                        rgb_buf.append(int(g * alpha + bg * (1.0 - alpha)))
                        rgb_buf.append(int(b * alpha + bb * (1.0 - alpha)))
                ppm_header = f"P6\n{pixel_w} {pixel_h}\n255\n".encode("ascii")
                ppm_data = ppm_header + bytes(rgb_buf)
                clean_b64 = base64.b64encode(ppm_data).decode("ascii")
        else:
            clean_b64 = base64.b64encode(raw_bytes).decode("ascii")

        stored_img = GraphicImage(
            image_id=img_id,
            format=img_format,
            data=raw_bytes,
            base64_data=clean_b64,
            pixel_width=pixel_w,
            pixel_height=pixel_h,
        )
        self.screen.store_graphic(stored_img)

        # Action 't' transmits and stores only (no placement or cursor advance)
        if action == "t":
            if self.write_response and quiet == 0:
                self.write_response(f"\x1b_Gi={img_id};OK\x1b\\".encode("ascii"))
            return

        # Action 'T' (or default) transmits and places on screen
        c_param = int(params.get("c", "0")) if params.get("c", "").isdigit() else 0
        r_param = int(params.get("r", "0")) if params.get("r", "").isdigit() else 0
        cell_w_est = 9
        cell_h_est = 18

        if c_param > 0 and r_param > 0:
            cols = min(self.screen.cols, c_param)
            rows = r_param
        elif c_param > 0:
            cols = min(self.screen.cols, c_param)
            if pixel_w > 0 and pixel_h > 0:
                target_w = cols * cell_w_est
                target_h = target_w * (pixel_h / pixel_w)
                rows = max(1, round(target_h / cell_h_est))
            else:
                rows = 5
        elif r_param > 0:
            rows = r_param
            if pixel_w > 0 and pixel_h > 0:
                target_h = rows * cell_h_est
                target_w = target_h * (pixel_w / pixel_h)
                cols = min(self.screen.cols, max(1, round(target_w / cell_w_est)))
            else:
                cols = min(self.screen.cols, 10)
        else:
            cols = min(self.screen.cols, max(1, (pixel_w + cell_w_est - 1) // cell_w_est) if pixel_w > 0 else 10)
            rows = max(1, (pixel_h + cell_h_est - 1) // cell_h_est) if pixel_h > 0 else 5

        cursor_advance = (params.get("C", "0") != "1")
        if placement_id == 0:
            self._next_placement_id += 1
            placement_id = self._next_placement_id

        placement = GraphicPlacement(
            image_id=img_id,
            placement_id=placement_id,
            data=raw_bytes,
            format=img_format,
            col=self.screen.cursor_x,
            row=self.screen.cursor_y,
            abs_row=self.screen.total_lines_scrolled + self.screen.cursor_y,
            cols=cols,
            rows=rows,
            pixel_width=pixel_w,
            pixel_height=pixel_h,
            cursor_advance=cursor_advance,
            base64_data=clean_b64,
        )
        self.screen.add_graphic_placement(placement)

        if cursor_advance:
            for _ in range(rows):
                self.screen.cursor_y += 1
                if self.screen.cursor_y > self.screen.scroll_bottom:
                    self.screen.scroll_up(1)
                    self.screen.cursor_y = self.screen.scroll_bottom
            self.screen.cursor_x = 0
            self.screen.wrap_pending = False

        if self.write_response and quiet == 0:
            self.write_response(f"\x1b_Gi={img_id};OK\x1b\\".encode("ascii"))

        if self.write_response and quiet == 0:
            self.write_response(f"\x1b_Gi={img_id};OK\x1b\\".encode("ascii"))

    def _handle_csi(self, char: str):
        if not self.params and not self.current_subparams and not self.current_param and char in ("?", ">", "=", "<"):
            self.csi_prefix = char
            if char == "?":
                self.private_mode = True
            elif char == ">":
                self.secondary_da = True
        elif "0" <= char <= "9":
            if len(self.current_param) < self.MAX_PARAM_DIGITS:
                self.current_param += char
        elif char == ":":
            if len(self.current_subparams) < self.MAX_SUBPARAMS:
                self.current_subparams.append(int(self.current_param) if self.current_param else 0)
            self.current_param = ""
        elif char == ";":
            if len(self.current_subparams) < self.MAX_SUBPARAMS:
                self.current_subparams.append(int(self.current_param) if self.current_param else 0)
            if len(self.params) < self.MAX_PARAMS:
                self.params.append(self.current_subparams)
            self.current_subparams = []
            self.current_param = ""
        elif 0x20 <= ord(char) <= 0x2F:
            if len(self.intermediate_bytes) < 16:
                self.intermediate_bytes += char
        elif 0x40 <= ord(char) <= 0x7E:
            if self.current_param or self.current_subparams or not self.params:
                if len(self.current_subparams) < self.MAX_SUBPARAMS:
                    self.current_subparams.append(int(self.current_param) if self.current_param else 0)
                if len(self.params) < self.MAX_PARAMS:
                    self.params.append(self.current_subparams)
            self._dispatch_csi(char)
            self.state = self.STATE_GROUND

    def _param(self, idx: int, default: int = 1) -> int:
        if idx < len(self.params) and self.params[idx]:
            val = self.params[idx][0]
            return val if val > 0 else default
        return default

    def _param_zero(self, idx: int, default: int = 0) -> int:
        if idx < len(self.params) and self.params[idx]:
            return self.params[idx][0]
        return default

    def _dispatch_csi(self, final: str):
        if self.private_mode and final in ("h", "l"):
            enable = (final == "h")
            modes = [group[0] for group in self.params if group] if self.params else [0]
            for mode in modes:
                if mode == 1:
                    self.application_cursor_keys = enable
                elif mode == 6:
                    self.screen.origin_mode = enable
                    self.screen.move_cursor(0, 0)
                elif mode == 7:
                    self.screen.auto_wrap = enable
                elif mode == 25:
                    self.screen.cursor_visible = enable
                elif mode in (47, 1047, 1049):
                    if enable:
                        self.screen.enter_alt_screen()
                    else:
                        self.screen.exit_alt_screen()
                elif mode == 1000:
                    self.mouse_tracking = enable
                elif mode == 1002:
                    self.mouse_tracking = enable
                    self.mouse_button_motion = enable
                elif mode == 1003:
                    self.mouse_tracking = enable
                    self.mouse_all_motion = enable
                elif mode == 1004:
                    self.focus_reporting = enable
                elif mode == 1006:
                    self.sgr_mouse_mode = enable
                elif mode == 2004:
                    self.bracketed_paste_mode = enable
                elif mode == 2026:
                    self.screen.synchronized_output = enable
                    if not enable:
                        self.screen.mark_all_dirty()
            return

        if final == "q" and self.intermediate_bytes == " ":
            # DECSCUSR - Set Cursor Style
            self.screen.cursor_style = self._param_zero(0, 1)
            return

        val1 = self._param(0, 1)

        if final == "A":
            self.screen.move_cursor(self.screen.cursor_y - val1, self.screen.cursor_x)
        elif final == "B":
            self.screen.move_cursor(self.screen.cursor_y + val1, self.screen.cursor_x)
        elif final == "C":
            self.screen.move_cursor(self.screen.cursor_y, min(self.screen.cols - 1, self.screen.cursor_x + val1))
        elif final == "D":
            self.screen.move_cursor(self.screen.cursor_y, max(0, self.screen.cursor_x - val1))
        elif final == "E":
            self.screen.move_cursor(self.screen.cursor_y + val1, 0)
        elif final == "F":
            self.screen.move_cursor(self.screen.cursor_y - val1, 0)
        elif final == "G":
            self.screen.move_cursor(self.screen.cursor_y, min(self.screen.cols - 1, max(0, val1 - 1)))
        elif final == "d":
            target_row = (self.screen.scroll_top + val1 - 1) if self.screen.origin_mode else (val1 - 1)
            self.screen.move_cursor(target_row, self.screen.cursor_x)
        elif final in ("H", "f"):
            row = (self.params[0][0] - 1) if (len(self.params) > 0 and self.params[0] and self.params[0][0] > 0) else 0
            col = (self.params[1][0] - 1) if (len(self.params) > 1 and self.params[1] and self.params[1][0] > 0) else 0
            target_row = (self.screen.scroll_top + row) if self.screen.origin_mode else row
            self.screen.move_cursor(target_row, col)
        elif final == "J":
            self.screen.erase_in_display(self._param_zero(0, 0))
        elif final == "K":
            self.screen.erase_in_line(self._param_zero(0, 0))
        elif final == "L":
            self.screen.insert_lines(val1)
        elif final == "M":
            self.screen.delete_lines(val1)
        elif final == "@":
            self.screen.insert_chars(val1)
        elif final == "P":
            self.screen.delete_chars(val1)
        elif final == "X":
            self.screen.erase_chars(val1)
        elif final == "S":
            self.screen.scroll_up(val1)
        elif final == "T":
            self.screen.scroll_down(val1)
        elif final == "s":
            self.screen.save_cursor()
        elif final == "m":
            self.screen.handle_sgr(self.params)
        elif final == "r":
            top = (self.params[0][0] - 1) if (len(self.params) > 0 and self.params[0] and self.params[0][0] > 0) else 0
            bottom = (self.params[1][0] - 1) if (len(self.params) > 1 and self.params[1] and self.params[1][0] > 0) else (self.screen.rows - 1)
            if 0 <= top < bottom < self.screen.rows:
                self.screen.scroll_top = top
                self.screen.scroll_bottom = bottom
                self.screen.move_cursor(0, 0)
        elif final == "c":
            if self.secondary_da:
                self._send_response(b"\x1b[>1;10;0c")
            else:
                self._send_response(b"\x1b[?62;c")
        elif final == "n":
            mode = self._param_zero(0, 0)
            if mode == 6:
                cpr = f"\x1b[{self.screen.cursor_y + 1};{self.screen.cursor_x + 1}R".encode("ascii")
                self._send_response(cpr)
            elif mode == 5:
                self._send_response(b"\x1b[0n")
        elif final == "u":
            if not self.csi_prefix:
                self.screen.restore_cursor()
            else:
                first_val = self._param_zero(0, 0)
                if self.csi_prefix == "?":
                    self._send_response(f"\x1b[?{self.kitty_keyboard_flags}u".encode("ascii"))
                elif self.csi_prefix == ">":
                    self.kitty_keyboard_stack.append(self.kitty_keyboard_flags)
                    self.kitty_keyboard_flags = first_val
                elif self.csi_prefix == "<":
                    pop_count = self._param(0, 1)
                    for _ in range(pop_count):
                        if self.kitty_keyboard_stack:
                            self.kitty_keyboard_flags = self.kitty_keyboard_stack.pop()
                        else:
                            self.kitty_keyboard_flags = 0
                elif self.csi_prefix == "=":
                    mode = self._param(1, 1)
                    if mode == 1:
                        self.kitty_keyboard_flags = first_val
                    elif mode == 2:
                        self.kitty_keyboard_flags |= first_val
                    elif mode == 3:
                        self.kitty_keyboard_flags &= ~first_val

    def _send_response(self, data: bytes):
        if self.write_response:
            self.write_response(data)

    def _handle_osc(self, char: str):
        if char in ("\x07", "\x9c"):
            self._dispatch_osc(self.osc_payload)
            self.state = self.STATE_GROUND
            self.escape_in_string = False
        elif self.escape_in_string:
            self.escape_in_string = False
            if char == "\\":
                self._dispatch_osc(self.osc_payload)
                self.state = self.STATE_GROUND
            elif char == "\x1b":
                self.escape_in_string = True
            elif len(self.osc_payload) < self.MAX_OSC_LENGTH:
                self.osc_payload += "\x1b" + char
        elif char == "\x1b":
            self.escape_in_string = True
        else:
            if len(self.osc_payload) < self.MAX_OSC_LENGTH:
                self.osc_payload += char

    def _dispatch_osc(self, payload: str):
        if payload.startswith(("0;", "2;")):
            parts = payload.split(";", 1)
            if len(parts) == 2:
                title = parts[1]
                self.screen.title = title
                if self.on_title_change:
                    self.on_title_change(title)
        elif payload.startswith("1;"):
            parts = payload.split(";", 1)
            if len(parts) == 2:
                self.screen.icon_name = parts[1]
        elif payload.startswith("7;"):
            parts = payload.split(";", 1)
            if len(parts) == 2:
                uri = parts[1]
                path: str | None = None
                if uri.startswith("file://"):
                    parsed = urllib.parse.urlparse(uri)
                    allowed_hosts = {"", "localhost", "127.0.0.1"}
                    try:
                        allowed_hosts.add(socket.gethostname().lower())
                    except OSError:
                        pass
                    try:
                        allowed_hosts.add(os.uname().nodename.lower())
                    except (AttributeError, OSError):
                        pass
                    netloc = (parsed.netloc or "").split("@")[-1].split(":")[0].lower()
                    if netloc in allowed_hosts:
                        candidate = urllib.parse.unquote(parsed.path)
                        if os.path.isdir(candidate):
                            path = candidate
                else:
                    candidate = urllib.parse.unquote(uri)
                    if os.path.isdir(candidate):
                        path = candidate
                if path:
                    self.screen.cwd = path
                    if self.on_cwd_change:
                        self.on_cwd_change(path)
        elif payload.startswith("8;"):
            parts = payload.split(";", 2)
            if len(parts) >= 3:
                url = parts[2]
                self.screen.current_url = url if url else None
        elif payload.startswith("9;"):
            parts = payload.split(";", 1)
            msg = parts[1] if len(parts) > 1 else ""
            if self.on_notification:
                self.on_notification("Terminal", msg)
        elif payload.startswith("52;"):
            parts = payload.split(";", 2)
            sel = parts[1] if len(parts) > 1 else ""
            data = parts[2] if len(parts) > 2 else (parts[1] if len(parts) == 2 else "")
            if data == "?":
                if self.on_clipboard_query:
                    text = self.on_clipboard_query(sel)
                    if text:
                        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
                        out_sel = sel or "c"
                        self._send_response(f"\x1b]52;{out_sel};{b64}\x1b\\".encode("ascii"))
            elif data:
                try:
                    if len(data) <= 1_000_000:
                        text = base64.b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
                        if self.on_clipboard_write:
                            self.on_clipboard_write(sel, text)
                except (ValueError, binascii.Error):
                    return
        elif payload.startswith("777;"):
            parts = payload.split(";")
            if len(parts) >= 4 and parts[1] == "notify":
                title = parts[2]
                msg = parts[3]
                if self.on_notification:
                    self.on_notification(title, msg)
        elif payload == "10;?" or payload.startswith("10;?"):
            fg_hex = f"{DEFAULT_FG[0]:02x}{DEFAULT_FG[0]:02x}/{DEFAULT_FG[1]:02x}{DEFAULT_FG[1]:02x}/{DEFAULT_FG[2]:02x}{DEFAULT_FG[2]:02x}"
            self._send_response(f"\x1b]10;rgb:{fg_hex}\x1b\\".encode("ascii"))
        elif payload == "11;?" or payload.startswith("11;?"):
            bg_hex = f"{DEFAULT_BG[0]:02x}{DEFAULT_BG[0]:02x}/{DEFAULT_BG[1]:02x}{DEFAULT_BG[1]:02x}/{DEFAULT_BG[2]:02x}{DEFAULT_BG[2]:02x}"
            self._send_response(f"\x1b]11;rgb:{bg_hex}\x1b\\".encode("ascii"))
        elif payload.startswith("133;"):
            parts = payload.split(";")
            cmd = parts[1] if len(parts) > 1 else ""
            if cmd == "A":
                self.screen.mark_prompt_start()
            elif cmd == "B":
                self.screen.mark_prompt_end()
            elif cmd == "C":
                self.screen.mark_command_executed()
            elif cmd == "D":
                exit_code = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
                self.screen.mark_command_finished(exit_code)
