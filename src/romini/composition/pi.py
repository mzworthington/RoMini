import subprocess


class SystemdHalt:
    def poweroff(self) -> None:
        subprocess.run(["systemctl", "poweroff"], check=False)


class MpvPlayer:
    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        subprocess.run(["mpv", "--ao=alsa", f"--start={position_sec}", path], check=False)

    def select(self, uid: str, path: str) -> None:
        return

    def selected_track(self) -> tuple[str, str] | None:
        return None

    def pause(self) -> None:
        return

    def stop(self) -> None:
        return

    def is_playing(self) -> bool:
        return False

    def playing_uid(self) -> str | None:
        return None

    def playing_path(self) -> str | None:
        return None


class Pn532Nfc:
    def __init__(self, reader: object) -> None:
        self._reader = reader

    def read_uid(self) -> str | None:
        uid = self._reader.read_passive_target()
        if uid is None:
            return None
        return bytes(uid).hex()
