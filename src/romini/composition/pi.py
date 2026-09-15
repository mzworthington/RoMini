import json
import subprocess


class SystemdHalt:
    def poweroff(self) -> None:
        subprocess.run(["systemctl", "poweroff"], check=False)


class MpvPlayer:
    def __init__(self, ipc=None, mixer=None) -> None:
        self._ipc = ipc
        self.mixer = mixer
        self._playing = False
        self._uid: str | None = None
        self._path: str | None = None
        self._selected: tuple[str, str] | None = None

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        cmd = [
            "mpv",
            "--ao=alsa",
            "--input-ipc-server=/tmp/romini-mpv.sock",
            f"--start={position_sec}",
        ]
        if self.mixer is not None:
            cmd.append(f"--volume={self.mixer.level}")
        cmd.append(path)
        subprocess.Popen(cmd)
        self._playing = True
        self._uid = uid
        self._path = path

    def select(self, uid: str, path: str) -> None:
        self._selected = (uid, path)

    def selected_track(self) -> tuple[str, str] | None:
        return self._selected

    def pause(self) -> None:
        if self._ipc is not None:
            self._ipc('{"command":["set_property","pause",true]}')
        self._playing = False

    def stop(self) -> None:
        if self._ipc is not None:
            self._ipc('{"command":["stop"]}')
        self._playing = False
        self._uid = None

    def is_playing(self) -> bool:
        return self._playing

    def playing_uid(self) -> str | None:
        return self._uid

    def playing_path(self) -> str | None:
        return self._path

    def set_volume(self, level: int) -> None:
        if self._ipc is None:
            return
        self._ipc(json.dumps({"command": ["set_property", "volume", level]}, separators=(",", ":")))

    def play_earcon(self, path: str) -> None:
        from importlib.resources import files

        name = path.rsplit("/", 1)[-1]
        wav = files("romini").joinpath(name)
        audio = str(wav) if wav.is_file() else path
        subprocess.Popen(["mpv", "--ao=alsa", audio])


class MpvIpcStatus:
    def __init__(self, connect=None, path: str = "/tmp/romini-mpv.sock") -> None:
        self._connect = connect
        self._path = path

    def is_playing(self) -> bool:
        import json

        connect = self._connect if self._connect is not None else _unix_connect
        try:
            sock = connect(self._path)
            sock.sendall(b'{"command":["get_property","pause"]}\n')
            payload = json.loads(sock.recv(4096).decode())
            sock.close()
        except OSError:
            return False
        return payload.get("data") is False


def _unix_connect(path: str) -> object:
    import socket

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(path)
    return sock


class Pn532Nfc:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def read_uid(self) -> str | None:
        uid = self._reader.read_passive_target()
        if uid is None:
            return None
        return bytes(uid).hex()
