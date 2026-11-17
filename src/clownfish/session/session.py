"""Terminal session managing buffer, parser, keyboard state, and transport."""

from __future__ import annotations

import codecs
import queue
from collections.abc import Callable
from typing import Any

from clownfish.core.keyboard import encode_key_press
from clownfish.core.parser import VT100Parser
from clownfish.core.screen import ScreenBuffer
from clownfish.session.transport import Transport

TransportFactory = Callable[[int, int], Transport]
_default_transport_factory: TransportFactory | None = None


def set_default_transport_factory(factory: TransportFactory | None) -> None:
    """Register a custom global factory function for creating default transports."""
    global _default_transport_factory
    _default_transport_factory = factory


def get_default_transport(cols: int, rows: int, cwd: str | None = None) -> Transport:
    """Create a default transport for the current platform."""
    if _default_transport_factory is not None:
        try:
            return _default_transport_factory(cols, rows, cwd)  # type: ignore
        except TypeError:
            return _default_transport_factory(cols, rows)
    try:
        from clownfish.transports.pty import PTYTransport

        return PTYTransport(cols=cols, rows=rows, cwd=cwd)
    except (ImportError, OSError) as err:
        raise RuntimeError(
            "No default PTY transport available on this platform. "
            "Please provide an explicit transport instance."
        ) from err


class TerminalSession:
    """Represents an active terminal session independent of any specific UI frontend."""

    def __init__(
        self,
        cols: int = 80,
        rows: int = 24,
        max_scrollback: int = 10_000,
        transport: Transport | None = None,
        title: str = "clownfish",
        on_title_changed: Callable[[str], None] | None = None,
        on_bell: Callable[[], None] | None = None,
        on_output: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
        auto_drain: bool = True,
        cwd: str | None = None,
        on_cwd_changed: Callable[[str], None] | None = None,
        on_notification: Callable[[str, str], None] | None = None,
        on_clipboard_write: Callable[[str, str], None] | None = None,
        on_clipboard_query: Callable[[str], str] | None = None,
    ) -> None:
        self.cols = cols
        self.rows = rows
        self.title = title
        self.cwd = cwd or ""
        self.auto_drain = auto_drain

        self.on_title_changed = on_title_changed
        self.on_bell = on_bell
        self.on_output = on_output
        self.on_close = on_close
        self.on_cwd_changed = on_cwd_changed
        self.on_notification = on_notification
        self.on_clipboard_write = on_clipboard_write
        self.on_clipboard_query = on_clipboard_query

        self.screen = ScreenBuffer(cols=cols, rows=rows, max_scrollback=max_scrollback)
        self.parser = VT100Parser(
            self.screen,
            write_response=self._on_parser_response,
            on_title_change=self._on_parser_title,
            on_cwd_change=self._on_parser_cwd,
            on_notification=self._on_parser_notification,
            on_clipboard_write=self._on_parser_clipboard_write,
            on_clipboard_query=self._on_parser_clipboard_query,
            on_bell=self._on_parser_bell,
        )
        self.utf8_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

        self.transport = transport if transport is not None else get_default_transport(cols, rows, cwd=self.cwd or None)
        self.transport.set_callbacks(
            on_data=self._on_transport_data,
            on_close=self._on_transport_close,
        )

        self._event_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=4096)
        self._event_notifier: Callable[[], None] | None = None

    def set_event_notifier(self, notifier: Callable[[], None] | None) -> None:
        """Register a callback to wake the main UI thread when new transport events arrive."""
        self._event_notifier = notifier

    def drain_events(self, max_bytes: int = 512_000) -> bool:
        """Drain and process pending transport events on the caller's thread.

        Returns True if more events remain pending in the queue after the batch limit.
        """
        bytes_processed = 0
        while not self._event_queue.empty():
            try:
                event_type, payload = self._event_queue.get_nowait()
            except queue.Empty:
                break

            if event_type == "data":
                bytes_processed += len(payload)
                text = self.utf8_decoder.decode(payload, final=False)
                self.parser.feed(text)
                if self.on_output:
                    self.on_output()
                if bytes_processed >= max_bytes:
                    return not self._event_queue.empty()
            elif event_type == "bell" and self.on_bell:
                self.on_bell()
            elif event_type == "close" and self.on_close:
                self.on_close()

        return False

    def start(self) -> None:
        """Start the transport layer."""
        self.transport.set_callbacks(
            on_data=self._on_transport_data,
            on_close=self._on_transport_close,
        )
        self.transport.start()

    def _on_parser_response(self, data: bytes) -> None:
        """Send responses generated by the VT100 parser (e.g. DSR, DA) back through transport."""
        self.transport.write(data)

    def _on_parser_title(self, title: str) -> None:
        """Propagate window/icon title changes from the parser."""
        self.title = title
        if self.on_title_changed is not None:
            self.on_title_changed(title)

    def _on_parser_cwd(self, cwd: str) -> None:
        """Propagate working directory changes from OSC 7."""
        self.cwd = cwd
        if self.on_cwd_changed is not None:
            self.on_cwd_changed(cwd)

    def _on_parser_notification(self, title: str, message: str) -> None:
        """Propagate desktop notifications from OSC 9/777."""
        if self.on_notification is not None:
            self.on_notification(title, message)

    def _on_parser_clipboard_write(self, selection: str, text: str) -> None:
        """Handle OSC 52 clipboard write."""
        if self.on_clipboard_write is not None:
            self.on_clipboard_write(selection, text)

    def _on_parser_clipboard_query(self, selection: str) -> str:
        """Handle OSC 52 clipboard query."""
        if self.on_clipboard_query is not None:
            return self.on_clipboard_query(selection)
        return ""

    def _on_parser_bell(self) -> None:
        """Propagate bell event triggered by parser."""
        self._enqueue_event("bell", None)
        if self.on_bell is not None:
            self.on_bell()

    def _enqueue_event(self, event_type: str, payload: Any) -> None:
        """Enqueue event with bounded backpressure."""
        try:
            self._event_queue.put_nowait((event_type, payload))
        except queue.Full:
            return
        if self._event_notifier is not None:
            self._event_notifier()
        elif self.auto_drain:
            self.drain_events()

    def _on_transport_data(self, raw_bytes: bytes) -> None:
        """Enqueue incoming raw bytes from the transport."""
        self._enqueue_event("data", raw_bytes)

    def _on_transport_close(self) -> None:
        """Enqueue transport disconnection."""
        self._enqueue_event("close", None)

    def feed_text(self, text: str) -> None:
        """Directly feed text to the session's VT100 parser."""
        self.parser.feed(text)
        if self.on_output:
            self.on_output()

    def feed_bytes(self, raw_bytes: bytes) -> None:
        """Directly feed byte stream to the session."""
        self._on_transport_data(raw_bytes)

    def write(self, data: bytes) -> None:
        """Write raw bytes directly to the session transport."""
        self.transport.write(data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize the session screen buffer and notify the transport."""
        self.cols = cols
        self.rows = rows
        self.screen.resize(cols, rows)
        self.transport.resize(cols, rows)

    def send_key(self, keysym: str, state: int = 0, char: str = "") -> bool:
        """Encode and send a keyboard event to the session transport."""
        self.screen.reset_view()
        encoded = encode_key_press(
            keysym=keysym,
            state=state,
            char=char,
            kitty_keyboard_flags=self.parser.kitty_keyboard_flags,
            application_cursor_keys=self.parser.application_cursor_keys,
        )
        if encoded is not None:
            self.write(encoded)
            return True
        return False

    def send_mouse(self, button: int, col: int, row: int, release: bool = False) -> bool:
        """Encode and send mouse event if mouse reporting is enabled."""
        if not self.parser.mouse_tracking:
            return False

        final = "m" if release else "M"
        if self.parser.sgr_mouse_mode:
            packet = f"\x1b[<{button};{col + 1};{row + 1}{final}".encode()
        else:
            cb = 32 + (button if not release else 3)
            cx = 32 + min(223, col + 1)
            cy = 32 + min(223, row + 1)
            packet = bytes([0x1b, ord("["), ord("M"), cb, cx, cy])

        self.write(packet)
        return True

    def paste(self, text: str) -> None:
        """Send pasted text to the transport, handling bracketed paste mode if active."""
        if not text:
            return
        self.screen.reset_view()
        payload = text.replace("\r\n", "\r").replace("\n", "\r")
        raw_bytes = payload.encode("utf-8")

        if self.parser.bracketed_paste_mode:
            stream = b"\x1b[200~" + raw_bytes + b"\x1b[201~"
        else:
            stream = raw_bytes

        self.write(stream)

    def clear(self, request_redraw: bool = True) -> None:
        """Clear all screen buffer contents and scrollback, requesting shell redraw if in primary screen."""
        self.screen.clear_all()
        if request_redraw and not self.screen.is_alt_screen:
            self.write(b"\x0c")

    def clear_scrollback(self) -> None:
        """Clear scrollback history without wiping visible screen buffer."""
        self.screen.clear_saved_lines()

    def jump_prompt(self, direction: int) -> int | None:
        """Navigate to previous or next semantic prompt marker."""
        new_offset = self.screen.get_prompt_jump_offset(direction)
        if new_offset is not None:
            self.screen.scroll_offset = new_offset
            self.screen.mark_all_dirty()
        return new_offset

    def has_foreground_process(self) -> bool:
        """Return True if a foreground process is running in the session transport."""
        checker = getattr(self.transport, "has_foreground_process", None)
        return bool(checker()) if callable(checker) else False

    def close(self) -> None:
        """Close the session and its transport."""
        self.transport.close()

    def is_alive(self) -> bool:
        """Return True if the underlying transport is still alive."""
        return self.transport.is_alive()
