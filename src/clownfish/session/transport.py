"""Transport abstraction for terminal input and output."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable


class Transport(ABC):
    """Abstract base class representing a communication transport for a terminal session."""

    def __init__(
        self,
        on_data: Callable[[bytes], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self._on_data = on_data
        self._on_close = on_close

    def set_callbacks(
        self,
        on_data: Callable[[bytes], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """Register callbacks for incoming data and transport closure."""
        if on_data is not None:
            self._on_data = on_data
        if on_close is not None:
            self._on_close = on_close

    @abstractmethod
    def start(self) -> None:
        """Start or initialize the transport connection."""

    @abstractmethod
    def write(self, data: bytes) -> None:
        """Write raw byte stream to the transport."""

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """Notify the remote end of a terminal dimensions change."""

    @abstractmethod
    def close(self) -> None:
        """Close the transport and release underlying resources."""

    @abstractmethod
    def is_alive(self) -> bool:
        """Return True if the transport is still running/connected."""
