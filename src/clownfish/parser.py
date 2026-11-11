"""VT100, ANSI, and OSC escape sequence parser."""

from collections.abc import Callable

from clownfish.models import DEFAULT_BG, DEFAULT_FG
from clownfish.screen import ScreenBuffer


class VT100Parser:
    """State machine parser decoding ANSI/VT100/OSC control streams."""

    STATE_GROUND = 0
    STATE_ESCAPE = 1
    STATE_CSI = 2
    STATE_OSC = 3
    STATE_STRING = 4  # DCS, APC, PM, SOS

    MAX_OSC_LENGTH: int = 8192
    MAX_STRING_LENGTH: int = 8192

    def __init__(
        self,
        screen: ScreenBuffer,
        write_response: Callable[[bytes], None] | None = None,
    ):
        self.screen = screen
        self.write_response = write_response
        self.state = self.STATE_GROUND
        self.params: list[int] = []
        self.current_param = ""
        self.private_mode = False
        self.secondary_da = False
        self.csi_prefix = ""
        self.intermediate_bytes = ""
        self.osc_payload = ""
        self.string_payload = ""

        # Terminal Flags
        self.application_cursor_keys = False
        self.bracketed_paste_mode = False
        self.mouse_tracking = False     # ?1000h (Normal tracking)
        self.sgr_mouse_mode = False      # ?1006h (SGR decimal format)
        self.kitty_keyboard_flags = 0
        self.kitty_keyboard_stack: list[int] = []

    def feed(self, text: str):
        for char in text:
            if self.state == self.STATE_GROUND:
                self._handle_ground(char)
            elif self.state == self.STATE_ESCAPE:
                self._handle_escape(char)
            elif self.state == self.STATE_CSI:
                self._handle_csi(char)
            elif self.state == self.STATE_OSC:
                self._handle_osc(char)
            elif self.state == self.STATE_STRING:
                self._handle_string(char)

    def _handle_ground(self, char: str):
        if char == "\x1b":
            self.state = self.STATE_ESCAPE
        elif char == "\r":
            self.screen.cursor_x = 0
        elif char in ("\n", "\x0b", "\x0c"):
            self.screen.cursor_y += 1
            if self.screen.cursor_y > self.screen.scroll_bottom:
                self.screen.scroll_up(1)
                self.screen.cursor_y = self.screen.scroll_bottom
        elif char == "\b":
            self.screen.cursor_x = max(0, self.screen.cursor_x - 1)
        elif char == "\t":
            self.screen.cursor_x = min(self.screen.cols - 1, (self.screen.cursor_x + 8) & ~7)
        elif ord(char) >= 32:
            self.screen.put_char(char)

    def _handle_escape(self, char: str):
        if char == "[":
            self.state = self.STATE_CSI
            self.params = []
            self.current_param = ""
            self.private_mode = False
            self.secondary_da = False
            self.csi_prefix = ""
            self.intermediate_bytes = ""
        elif char == "]":
            self.state = self.STATE_OSC
            self.osc_payload = ""
        elif char in ("P", "_", "^", "X"):
            # P: DCS (Device Control String)
            # _: APC (Application Program Command)
            # ^: PM (Privacy Message)
            # X: SOS (Start of String)
            self.state = self.STATE_STRING
            self.string_payload = ""
        elif char == "7":
            self.screen.save_cursor()
            self.state = self.STATE_GROUND
        elif char == "8":
            self.screen.restore_cursor()
            self.state = self.STATE_GROUND
        elif char == "M":
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
        if char in ("\x07", "\x9c") or char == "\\" and self.string_payload.endswith("\x1b"):
            self.state = self.STATE_GROUND
        else:
            if len(self.string_payload) < self.MAX_STRING_LENGTH:
                self.string_payload += char

    def _handle_csi(self, char: str):
        if not self.params and not self.current_param and char in ("?", ">", "=", "<"):
            self.csi_prefix = char
            if char == "?":
                self.private_mode = True
            elif char == ">":
                self.secondary_da = True
        elif "0" <= char <= "9":
            self.current_param += char
        elif char in (";", ":"):
            self.params.append(int(self.current_param) if self.current_param else 0)
            self.current_param = ""
        elif 0x20 <= ord(char) <= 0x2F:
            # Intermediate byte (ECMA-48 range 0x20-0x2F)
            self.intermediate_bytes += char
        elif 0x40 <= ord(char) <= 0x7E:
            if self.current_param:
                self.params.append(int(self.current_param))
            self._dispatch_csi(char)
            self.state = self.STATE_GROUND

    def _dispatch_csi(self, final: str):
        p = self.params
        val1 = p[0] if (p and p[0] > 0) else 1

        if self.private_mode and final in ("h", "l"):
            enable = (final == "h")
            for mode in (p if p else [0]):
                if mode == 1:
                    self.application_cursor_keys = enable
                elif mode == 25:
                    self.screen.cursor_visible = enable
                elif mode in (47, 1047, 1049):
                    if enable:
                        self.screen.enter_alt_screen()
                    else:
                        self.screen.exit_alt_screen()
                elif mode == 2004:
                    self.bracketed_paste_mode = enable
                elif mode == 1000:
                    self.mouse_tracking = enable
                elif mode == 1006:
                    self.sgr_mouse_mode = enable
            return

        if final == "A":
            self.screen.cursor_y = max(0, self.screen.cursor_y - val1)
        elif final == "B":
            self.screen.cursor_y = min(self.screen.rows - 1, self.screen.cursor_y + val1)
        elif final == "C":
            self.screen.cursor_x = min(self.screen.cols - 1, self.screen.cursor_x + val1)
        elif final == "D":
            self.screen.cursor_x = max(0, self.screen.cursor_x - val1)
        elif final == "G":
            self.screen.cursor_x = min(self.screen.cols - 1, max(0, val1 - 1))
        elif final == "d":
            self.screen.cursor_y = min(self.screen.rows - 1, max(0, val1 - 1))
        elif final in ("H", "f"):
            row = (p[0] - 1) if (len(p) > 0 and p[0] > 0) else 0
            col = (p[1] - 1) if (len(p) > 1 and p[1] > 0) else 0
            self.screen.move_cursor(row, col)
        elif final == "J":
            self.screen.erase_in_display(p[0] if p else 0)
        elif final == "K":
            self.screen.erase_in_line(p[0] if p else 0)
        elif final == "@":
            self.screen.insert_chars(val1)
        elif final == "P":
            self.screen.delete_chars(val1)
        elif final == "m":
            self.screen.handle_sgr(p)
        elif final == "r":
            top = (p[0] - 1) if (len(p) > 0 and p[0] > 0) else 0
            bottom = (p[1] - 1) if (len(p) > 1 and p[1] > 0) else (self.screen.rows - 1)
            if 0 <= top < bottom < self.screen.rows:
                self.screen.scroll_top = top
                self.screen.scroll_bottom = bottom
                self.screen.move_cursor(0, 0)
        elif final == "c":
            if self.secondary_da:
                # Secondary Device Attributes (DA2) - VT220/xterm
                self._send_response(b"\x1b[>1;10;0c")
            else:
                # Primary Device Attributes (DA1) - VT220 response
                self._send_response(b"\x1b[?62;c")
        elif final == "n":
            if p and p[0] == 6:
                # Device Status Report / Cursor Position Query (CPR)
                cpr = f"\x1b[{self.screen.cursor_y + 1};{self.screen.cursor_x + 1}R".encode("ascii")
                self._send_response(cpr)
            elif p and p[0] == 5:
                # Terminal status OK
                self._send_response(b"\x1b[0n")
        elif final == "u":
            # Kitty Extended Keyboard Protocol negotiation
            if self.csi_prefix == "?":
                # Query keyboard protocol flags
                self._send_response(f"\x1b[?{self.kitty_keyboard_flags}u".encode("ascii"))
            elif self.csi_prefix == ">":
                # Push flags
                self.kitty_keyboard_stack.append(self.kitty_keyboard_flags)
                self.kitty_keyboard_flags = p[0] if p else 0
            elif self.csi_prefix == "<":
                # Pop flags
                pop_count = p[0] if p else 1
                for _ in range(pop_count):
                    if self.kitty_keyboard_stack:
                        self.kitty_keyboard_flags = self.kitty_keyboard_stack.pop()
                    else:
                        self.kitty_keyboard_flags = 0
            elif self.csi_prefix == "=":
                # Set flags
                self.kitty_keyboard_flags = p[0] if p else 0

    def _send_response(self, data: bytes):
        if self.write_response:
            self.write_response(data)

    def _handle_osc(self, char: str):
        if char in ("\x07", "\x9c"):
            self._dispatch_osc(self.osc_payload)
            self.state = self.STATE_GROUND
        elif char == "\\" and self.osc_payload.endswith("\x1b"):
            self._dispatch_osc(self.osc_payload[:-1])
            self.state = self.STATE_GROUND
        else:
            if len(self.osc_payload) < self.MAX_OSC_LENGTH:
                self.osc_payload += char

    def _dispatch_osc(self, payload: str):
        # OSC 8 Hyperlink: 8;params;URL
        if payload.startswith("8;"):
            parts = payload.split(";", 2)
            if len(parts) >= 3:
                url = parts[2]
                self.screen.current_url = url if url else None
        # OSC 10 / OSC 11 Color Queries
        elif payload == "10;?" or payload.startswith("10;?"):
            fg_hex = f"{DEFAULT_FG[0]:02x}{DEFAULT_FG[0]:02x}/{DEFAULT_FG[1]:02x}{DEFAULT_FG[1]:02x}/{DEFAULT_FG[2]:02x}{DEFAULT_FG[2]:02x}"
            self._send_response(f"\x1b]10;rgb:{fg_hex}\x1b\\".encode("ascii"))
        elif payload == "11;?" or payload.startswith("11;?"):
            bg_hex = f"{DEFAULT_BG[0]:02x}{DEFAULT_BG[0]:02x}/{DEFAULT_BG[1]:02x}{DEFAULT_BG[1]:02x}/{DEFAULT_BG[2]:02x}{DEFAULT_BG[2]:02x}"
            self._send_response(f"\x1b]11;rgb:{bg_hex}\x1b\\".encode("ascii"))
        # OSC 133 Semantic Prompts / Shell Integration
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
