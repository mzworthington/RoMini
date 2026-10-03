from pathlib import Path
from time import sleep

from romini.composition.host_power import HostPower


def _wait_for(commands: list[list[str]]) -> None:
    for _ in range(50):
        if commands:
            return
        sleep(0.01)


def test_host_power_returns_before_the_wifi_command_finishes(tmp_path: Path) -> None:
    from threading import Event

    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    (cpu / "scaling_governor").write_text("ondemand\n")
    release = Event()
    finished = Event()

    def run(cmd: list[str]) -> None:
        release.wait(timeout=0.4)
        finished.set()

    HostPower(sys_root=tmp_path, run=run).apply(playing=False, radio_sleep=True)

    assert not finished.is_set()
    release.set()


def test_host_power_sets_powersave_and_wifi_sleep_once(tmp_path: Path) -> None:
    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    governor = cpu / "scaling_governor"
    governor.write_text("ondemand\n")
    commands: list[list[str]] = []
    power = HostPower(sys_root=tmp_path, run=commands.append)

    power.apply(playing=False, radio_sleep=True)
    power.apply(playing=False, radio_sleep=True)
    _wait_for(commands)

    assert governor.read_text() == "powersave"
    assert commands == [["iw", "dev", "wlan0", "set", "power_save", "on"]]


def test_host_power_uses_ondemand_and_wakes_wifi_while_playing(tmp_path: Path) -> None:
    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    governor = cpu / "scaling_governor"
    governor.write_text("powersave\n")
    commands: list[list[str]] = []
    power = HostPower(sys_root=tmp_path, run=commands.append)

    power.apply(playing=True, radio_sleep=False)
    _wait_for(commands)

    assert governor.read_text() == "ondemand"
    assert commands == [["iw", "dev", "wlan0", "set", "power_save", "off"]]
