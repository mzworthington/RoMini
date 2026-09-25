from pathlib import Path

from romini.composition.host_power import HostPower


def test_host_power_sets_powersave_and_wifi_sleep_once(tmp_path: Path) -> None:
    cpu = tmp_path / "devices/system/cpu/cpu0/cpufreq"
    cpu.mkdir(parents=True)
    governor = cpu / "scaling_governor"
    governor.write_text("ondemand\n")
    commands: list[list[str]] = []
    power = HostPower(sys_root=tmp_path, run=commands.append)

    power.apply(playing=False, radio_sleep=True)
    power.apply(playing=False, radio_sleep=True)

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

    assert governor.read_text() == "ondemand"
    assert commands == [["iw", "dev", "wlan0", "set", "power_save", "off"]]
