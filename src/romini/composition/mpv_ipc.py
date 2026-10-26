import json
import socket
from os import environ
from pathlib import Path


def mpv_ipc_socket() -> str:
    runtime = environ.get("RUNTIME_DIRECTORY") or environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return str(Path(runtime) / "mpv.sock")
    home = Path.home() / ".romini"
    home.mkdir(mode=0o700, exist_ok=True)
    return str(home / "mpv.sock")


def unix_connect(path: str) -> object:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    return sock


class MpvIpcStatus:
    def __init__(self, connect=None, path: str | None = None) -> None:
        self._connect = connect
        self._path = path if path is not None else mpv_ipc_socket()

    def is_playing(self) -> bool:
        connect = self._connect if self._connect is not None else unix_connect
        try:
            sock = connect(self._path)
            sock.sendall(b'{"command":["get_property","pause"]}\n')
            payload = json.loads(sock.recv(4096).decode())
            sock.close()
        except OSError:
            return False
        return payload.get("data") is False
