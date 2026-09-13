from romini.composition.pi import MpvPlayer, Pn532Nfc, SystemdHalt


def test_systemd_halt_runs_systemctl_poweroff(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    SystemdHalt().poweroff()

    assert calls == [["systemctl", "poweroff"]]


def test_mpv_player_starts_track_on_alsa(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    MpvPlayer().play("/var/lib/romini/library/frog.mp3", position_sec=14.5, uid="04AABBCC")

    assert calls == [
        [
            "mpv",
            "--ao=alsa",
            "--input-ipc-server=/tmp/romini-mpv.sock",
            "--start=14.5",
            "/var/lib/romini/library/frog.mp3",
        ]
    ]


def test_pn532_nfc_reads_uid_as_lowercase_hex() -> None:
    class Reader:
        def read_passive_target(self) -> bytes:
            return bytes.fromhex("04aabbccddeeff")

    assert Pn532Nfc(Reader()).read_uid() == "04aabbccddeeff"


def test_mpv_player_pause_sends_ipc_command(monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr("romini.composition.pi.subprocess.run", lambda *args, **kwargs: None)
    player = MpvPlayer(ipc=sent.append)
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04aabbcc")
    player.pause()

    assert '{"command":["set_property","pause",true]}' in sent[0]
    assert player.is_playing() is False


def test_rpi_gpio_led_driver_pulses_pin_high_then_low() -> None:
    from romini.composition.gpio import GPIO_LED, GpioLed, RpiGpioLedDriver

    class Gpio:
        BCM = 11
        OUT = 0
        HIGH = 1
        LOW = 0
        modes: list[int] = []
        setups: list[tuple[int, int]] = []
        outputs: list[tuple[int, int]] = []

        def setmode(self, mode: int) -> None:
            self.modes.append(mode)

        def setup(self, pin: int, mode: int) -> None:
            self.setups.append((pin, mode))

        def output(self, pin: int, value: int) -> None:
            self.outputs.append((pin, value))

    gpio = Gpio()
    GpioLed(RpiGpioLedDriver(gpio)).pulse()

    assert gpio.modes == [Gpio.BCM]
    assert gpio.setups == [(GPIO_LED, Gpio.OUT)]
    assert gpio.outputs == [(GPIO_LED, Gpio.HIGH), (GPIO_LED, Gpio.LOW)]
