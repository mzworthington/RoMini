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


def test_host_power_idles_the_cpu_and_keeps_the_radio_awake(tmp_path: Path) -> None:
    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    governor = cpu / "scaling_governor"
    governor.write_text("ondemand\n")
    commands: list[list[str]] = []
    power = HostPower(sys_root=tmp_path, run=commands.append, clock=lambda: 0.0)

    power.apply(playing=False, radio_sleep=True)
    power.apply(playing=False, radio_sleep=True)
    _wait_for(commands)

    assert governor.read_text() == "powersave"
    assert commands == [["sudo", "-n", "/usr/sbin/iw", "dev", "wlan0", "set", "power_save", "off"]]


def test_host_power_holds_the_radio_awake_again_after_the_quiet_gap(tmp_path: Path) -> None:
    from romini.features.power.host import RADIO_HOLD_SEC

    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    (cpu / "scaling_governor").write_text("powersave\n")
    commands: list[list[str]] = []
    now = [0.0]
    power = HostPower(sys_root=tmp_path, run=commands.append, clock=lambda: now[0])

    power.apply(playing=False, radio_sleep=False)
    _wait_for(commands)
    now[0] = RADIO_HOLD_SEC
    power.apply(playing=False, radio_sleep=False)
    for _ in range(50):
        if len(commands) == 2:
            break
        sleep(0.01)

    assert len(commands) == 2
    assert commands[0] == commands[1]
    assert "power_save" in commands[0]
    assert "off" in commands[0]


def test_host_power_uses_ondemand_and_keeps_wifi_awake_while_playing(tmp_path: Path) -> None:
    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    governor = cpu / "scaling_governor"
    governor.write_text("powersave\n")
    commands: list[list[str]] = []
    power = HostPower(sys_root=tmp_path, run=commands.append)

    power.apply(playing=True, radio_sleep=False)
    _wait_for(commands)

    assert governor.read_text() == "ondemand"
    assert commands == [["sudo", "-n", "/usr/sbin/iw", "dev", "wlan0", "set", "power_save", "off"]]
