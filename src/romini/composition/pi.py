import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from importlib.resources import files
from os import environ
from pathlib import Path


def mpv_ipc_socket() -> str:
    runtime = environ.get("RUNTIME_DIRECTORY") or environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return str(Path(runtime) / "mpv.sock")
    home = Path.home() / ".romini"
    home.mkdir(mode=0o700, exist_ok=True)
    return str(home / "mpv.sock")


class SystemdHalt:
    def poweroff(self) -> None:
        subprocess.run(["systemctl", "poweroff"], check=False)


class MpvPlayer:
    def __init__(
        self, ipc=None, mixer=None, connect=None, clock: Callable[[], datetime] = datetime.now, alsa=None
    ) -> None:
        self._ipc = ipc
        self.mixer = mixer
        self._connect = connect
        self._clock = clock
        self._alsa = alsa
        self._playing = False
        self._uid: str | None = None
        self._path: str | None = None
        self._selected: tuple[str, str] | None = None
        self._started_at: datetime | None = None
        self._proc: object | None = None

    def _end_mpv(self) -> None:
        previous = self._proc
        self._proc = None
        if previous is None:
            return
        terminate = getattr(previous, "terminate", None)
        if callable(terminate):
            terminate()
        wait = getattr(previous, "wait", None)
        if callable(wait):
            try:
                wait(timeout=1)
            except subprocess.TimeoutExpired:
                kill = getattr(previous, "kill", None)
                if callable(kill):
                    kill()
                    wait(timeout=1)

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        cmd = [
            "mpv",
            "--ao=alsa",
            "--audio-device=alsa/sysdefault:CARD=Headphones",
            f"--input-ipc-server={mpv_ipc_socket()}",
            f"--start={position_sec}",
        ]
        if self.mixer is not None:
            cmd.append(f"--volume={self.mixer.level}")
            self._apply_alsa(self.mixer.level)
        cmd.append(path)
        self._end_mpv()
        self._proc = subprocess.Popen(cmd)
        self._playing = True
        self._uid = uid
        self._path = path
        self._started_at = self._clock()

    def select(self, uid: str, path: str) -> None:
        self._selected = (uid, path)

    def selected_track(self) -> tuple[str, str] | None:
        return self._selected

    def pause(self) -> None:
        if self._ipc is not None:
            self._ipc('{"command":["set_property","pause",true]}')
        self._end_mpv()
        self._playing = False

    def stop(self) -> None:
        if self._ipc is not None:
            self._ipc('{"command":["stop"]}')
        self._end_mpv()
        self._playing = False
        self._uid = None

    def is_playing(self) -> bool:
        return self._playing

    def playing_uid(self) -> str | None:
        return self._uid

    def playing_path(self) -> str | None:
        return self._path

    def started_at(self) -> datetime | None:
        return self._started_at

    def position_sec(self) -> float:
        connect = self._connect if self._connect is not None else _unix_connect
        try:
            sock = connect(mpv_ipc_socket())
            sock.sendall(b'{"command":["get_property","time-pos"]}\n')
            payload = json.loads(sock.recv(4096).decode())
            sock.close()
        except OSError:
            return 0.0
        data = payload.get("data")
        if isinstance(data, int | float):
            return float(data)
        return 0.0

    def set_volume(self, level: int) -> None:
        self._apply_alsa(level)
        payload = json.dumps({"command": ["set_property", "volume", level]}, separators=(",", ":"))
        if self._ipc is not None:
            self._ipc(payload)
            return
        try:
            sock = _unix_connect(mpv_ipc_socket())
            sock.sendall(payload.encode() + b"\n")
            sock.close()
        except OSError:
            return

    def _apply_alsa(self, level: int) -> None:
        cmd = ["amixer", "-c", "Headphones", "--", "sset", "Headphone", f"{level}%"]
        apply_alsa = self._alsa if self._alsa is not None else _alsa_run
        try:
            apply_alsa(cmd)
        except OSError:
            return

    def play_earcon(self, path: str) -> None:
        name = path.rsplit("/", 1)[-1]
        wav = files("romini").joinpath(name)
        audio = str(wav) if wav.is_file() else path
        proc = subprocess.Popen(["mpv", "--ao=alsa", "--audio-device=alsa/sysdefault:CARD=Headphones", audio])
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=1)


class MpvIpcStatus:
    def __init__(self, connect=None, path: str | None = None) -> None:
        self._connect = connect
        self._path = path if path is not None else mpv_ipc_socket()

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


def _alsa_run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False)


class Pn532Nfc:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def read_uid(self) -> str | None:
        uid = self._reader.read_passive_target()
        if uid is None:
            return None
        return bytes(uid).hex()

    def rest(self) -> None:
        power_down = getattr(self._reader, "power_down", None)
        if callable(power_down):
            power_down()
