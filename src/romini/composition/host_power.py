import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from time import monotonic

from romini.features.power.host import RADIO_HOLD_SEC, cpu_governor

_RADIO_AWAKE = ["sudo", "-n", "/usr/sbin/iw", "dev", "wlan0", "set", "power_save", "off"]


class HostPower:
    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        run: Callable[[list[str]], None] | None = None,
        clock: Callable[[], float] = monotonic,
        hold_sec: float = RADIO_HOLD_SEC,
    ) -> None:
        self._root = sys_root
        self._run = run if run is not None else _run
        self._clock = clock
        self._hold_sec = hold_sec
        self._governor = ""
        self._radio_until = 0.0

    def apply(self, *, playing: bool, radio_sleep: bool) -> None:
        del radio_sleep
        governor = cpu_governor(playing=playing)
        if governor != self._governor:
            for path in self._root.glob("devices/system/cpu/cpu*/cpufreq/scaling_governor"):
                path.write_text(governor)
            self._governor = governor
        now = self._clock()
        if now < self._radio_until:
            return
        self._radio_until = now + self._hold_sec
        Thread(
            target=self._run,
            args=(_RADIO_AWAKE,),
            daemon=True,
        ).start()


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False)
