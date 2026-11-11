"""SSH transport running an interactive remote terminal session."""

from __future__ import annotations

from collections.abc import Callable

from clownfish.transports.pty import PTYTransport


class SSHTransport(PTYTransport):
    """Transport connecting to a remote host using an interactive OpenSSH session."""

    def __init__(
        self,
        host: str,
        port: int = 22,
        user: str | None = None,
        identity_file: str | None = None,
        cols: int = 80,
        rows: int = 24,
        extra_args: list[str] | None = None,
        ssh_binary: str = "ssh",
        on_data: Callable[[bytes], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.identity_file = identity_file
        self.extra_args = extra_args or []
        self.ssh_binary = ssh_binary

        command = self._build_ssh_command()
        super().__init__(
            command=command,
            cols=cols,
            rows=rows,
            on_data=on_data,
            on_close=on_close,
        )

    def _build_ssh_command(self) -> list[str]:
        """Construct the OpenSSH command-line arguments."""
        cmd = [self.ssh_binary, "-tt"]
        if self.port != 22:
            cmd.extend(["-p", str(self.port)])
        if self.user:
            cmd.extend(["-l", self.user])
        if self.identity_file:
            cmd.extend(["-i", self.identity_file])
        cmd.extend(self.extra_args)
        cmd.append(self.host)
        return cmd
