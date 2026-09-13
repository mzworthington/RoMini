import subprocess


class SystemdHalt:
    def poweroff(self) -> None:
        subprocess.run(["systemctl", "poweroff"], check=False)


class MpvPlayer:
    def __init__(self, ipc=None) -> None:
        self._ipc = ipc
        self._playing = False
        self._uid: str | None = None
        self._path: str | None = None
        self._selected: tuple[str, str] | None = None

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        subprocess.run(
            ["mpv", "--ao=alsa", "--input-ipc-server=/tmp/romini-mpv.sock", f"--start={position_sec}", path],
            check=False,
        )
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


class Pn532Nfc:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def read_uid(self) -> str | None:
        uid = self._reader.read_passive_target()
        if uid is None:
            return None
        return bytes(uid).hex()
