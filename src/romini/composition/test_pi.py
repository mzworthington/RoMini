from romini.composition.pi import MpvPlayer, Pn532Nfc, SystemdHalt


def test_systemd_halt_runs_systemctl_poweroff(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    SystemdHalt().poweroff()

    assert calls == [["systemctl", "poweroff"]]


def test_mpv_player_starts_track_on_alsa(monkeypatch, tmp_path) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir()
    monkeypatch.setenv("RUNTIME_DIRECTORY", str(runtime))
    calls: list[list[str]] = []

    def popen(cmd: list[str], *args, **kwargs) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    MpvPlayer().play("/var/lib/romini/library/frog.mp3", position_sec=14.5, uid="04AABBCC")

    sock = runtime / "mpv.sock"
    assert calls == [
        [
            "mpv",
            "--ao=alsa",
            f"--input-ipc-server={sock}",
            "--start=14.5",
            "/var/lib/romini/library/frog.mp3",
        ]
    ]
    assert "/tmp/" not in str(sock)


def test_mpv_player_play_uses_mixer_level(monkeypatch) -> None:
    from romini.composition.mixer import MemoryMixer

    calls: list[list[str]] = []

    def popen(cmd: list[str], *args, **kwargs) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    MpvPlayer(mixer=MemoryMixer(level=42)).play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04AABBCC")

    assert "--volume=42" in calls[0]


def test_mpv_player_set_volume_sends_ipc() -> None:
    sent: list[str] = []
    MpvPlayer(ipc=sent.append).set_volume(42)

    assert sent == ['{"command":["set_property","volume",42]}']


def test_mpv_player_play_earcon_starts_mpv(monkeypatch) -> None:
    calls: list[list[str]] = []

    def popen(cmd: list[str], *args, **kwargs) -> object:
        calls.append(cmd)
        return object()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    MpvPlayer().play_earcon("romini/connect.wav")

    assert calls[0][:2] == ["mpv", "--ao=alsa"]
    assert calls[0][-1].endswith("connect.wav")


def test_pn532_nfc_reads_uid_as_lowercase_hex() -> None:
    class Reader:
        def read_passive_target(self) -> bytes:
            return bytes.fromhex("04aabbccddeeff")

    assert Pn532Nfc(Reader()).read_uid() == "04aabbccddeeff"


def test_mpv_player_pause_sends_ipc_command(monkeypatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", lambda *args, **kwargs: object())
    player = MpvPlayer(ipc=sent.append)
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04aabbcc")
    player.pause()

    assert '{"command":["set_property","pause",true]}' in sent[0]
    assert player.is_playing() is False


def test_mpv_player_play_does_not_wait_for_the_track_to_end(monkeypatch) -> None:
    started: list[list[str]] = []

    def popen(cmd: list[str], *args, **kwargs) -> object:
        started.append(cmd)

        class Proc:
            def poll(self) -> None:
                return None

        return Proc()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    player = MpvPlayer()
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04aabbcc")

    assert started[0][0] == "mpv"
    assert player.is_playing() is True


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


def test_mpv_ipc_status_is_playing_when_pause_is_false() -> None:
    from romini.composition.pi import MpvIpcStatus

    sent: list[bytes] = []

    class Sock:
        def sendall(self, data: bytes) -> None:
            sent.append(data)

        def recv(self, n: int) -> bytes:
            return b'{"data":false,"error":"success"}\n'

        def close(self) -> None:
            return

    assert MpvIpcStatus(connect=lambda path: Sock()).is_playing() is True
    assert b"pause" in sent[0]


def test_mpv_ipc_status_not_playing_when_socket_missing() -> None:
    from romini.composition.pi import MpvIpcStatus

    def connect(path: str) -> object:
        raise FileNotFoundError(path)

    assert MpvIpcStatus(connect=connect).is_playing() is False
