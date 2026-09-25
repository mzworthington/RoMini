from collections.abc import Callable
from pathlib import Path

from romini.features.power.host import cpu_governor


class HostPower:
    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        run: Callable[[list[str]], None] | None = None,
    ) -> None:
        self._root = sys_root
        self._run = run if run is not None else _run
        self._governor = ""
        self._radio_sleep: bool | None = None

    def apply(self, *, playing: bool, radio_sleep: bool) -> None:
        governor = cpu_governor(playing=playing)
        if governor != self._governor:
            for path in self._root.glob("devices/system/cpu/cpu*/cpufreq/scaling_governor"):
                path.write_text(governor)
            self._governor = governor
        if radio_sleep is self._radio_sleep:
            return
        state = "on" if radio_sleep else "off"
        self._run(["iw", "dev", "wlan0", "set", "power_save", state])
        self._radio_sleep = radio_sleep


def _run(cmd: list[str]) -> None:
    import subprocess

    subprocess.run(cmd, check=False)
