import subprocess
from typing import Protocol


class BoxPower(Protocol):
    def restart(self) -> None: ...

    def reboot(self) -> None: ...

    def poweroff(self) -> None: ...


class LocalPower:
    def __init__(self, *, halt: object | None, profile: str) -> None:
        self._halt = halt
        self._profile = profile

    def restart(self) -> None:
        self._system("restart", "romini-core")

    def reboot(self) -> None:
        self._system("reboot")

    def poweroff(self) -> None:
        if self._halt is not None:
            poweroff = getattr(self._halt, "poweroff", None)
            if callable(poweroff):
                poweroff()
                return
        self._system("poweroff")

    def _system(self, *args: str) -> None:
        if self._profile != "pi":
            return
        subprocess.run(["systemctl", *args], check=False)
