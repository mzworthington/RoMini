import subprocess
from pathlib import Path

from romini.composition.pi import MpvPlayer, Pn532Nfc, SystemdHalt


def test_systemd_halt_runs_systemctl_poweroff(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.pi.subprocess.run", run)
    SystemdHalt().poweroff()

    assert calls == [["systemctl", "poweroff"]]


def test_mpv_player_starts_track_on_alsa(monkeypatch) -> None:
    runtime = Path("/run/romini")
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
            "--audio-device=alsa/sysdefault:CARD=Headphones",
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
    MpvPlayer(mixer=MemoryMixer(level=42), alsa=lambda cmd: None).play(
        "/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04AABBCC"
    )

    assert "--volume=42" in calls[0]


def test_mpv_player_set_volume_sends_ipc() -> None:
    sent: list[str] = []
    MpvPlayer(ipc=sent.append).set_volume(42)

    assert sent == ['{"command":["set_property","volume",42]}']


def test_mpv_player_set_volume_sets_alsa_headphone() -> None:
    sent: list[list[str]] = []
    MpvPlayer(alsa=sent.append).set_volume(42)

    assert sent == [["amixer", "-c", "Headphones", "--", "sset", "Headphone", "42%"]]


def test_mpv_player_play_sets_alsa_headphone(monkeypatch) -> None:
    from romini.composition.mixer import MemoryMixer

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", lambda *args, **kwargs: object())
    sent: list[list[str]] = []
    MpvPlayer(mixer=MemoryMixer(level=42), alsa=sent.append).play(
        "/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04AABBCC"
    )

    assert sent == [["amixer", "-c", "Headphones", "--", "sset", "Headphone", "42%"]]


def test_mpv_player_play_earcon_starts_mpv(monkeypatch) -> None:
    calls: list[list[str]] = []

    class Proc:
        def wait(self, timeout: float | None = None) -> int:
            return 0

    def popen(cmd: list[str], *args, **kwargs) -> Proc:
        calls.append(cmd)
        return Proc()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    MpvPlayer().play_earcon("romini/connect.wav")

    assert calls[0][:3] == [
        "mpv",
        "--ao=alsa",
        "--audio-device=alsa/sysdefault:CARD=Headphones",
    ]
    assert calls[0][-1].endswith("connect.wav")


def test_mpv_chime_releases_the_headphones_before_the_story_starts(monkeypatch) -> None:
    order: list[str] = []

    class Proc:
        def wait(self, timeout: float | None = None) -> int:
            order.append("chime-done")
            return 0

    def popen(cmd: list[str], *args, **kwargs) -> object:
        if str(cmd[-1]).endswith("connect.wav"):
            order.append("chime-start")
            return Proc()
        order.append("story-start")
        return object()

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    player = MpvPlayer()
    player.play_earcon("romini/connect.wav")
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04AABBCC")

    assert order.index("chime-done") < order.index("story-start")


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


def test_mpv_player_play_terminates_the_previous_track(monkeypatch) -> None:
    class Proc:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    procs: list[Proc] = []

    def popen(cmd: list[str], *args, **kwargs) -> Proc:
        proc = Proc()
        procs.append(proc)
        return proc

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    player = MpvPlayer()
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="aaa")
    player.play("/var/lib/romini/library/helmet.mp3", position_sec=0.0, uid="bbb")

    assert procs[0].terminated is True
    assert procs[1].terminated is False


def test_mpv_player_play_waits_for_the_previous_track_to_exit(monkeypatch) -> None:
    class Proc:
        def __init__(self) -> None:
            self.terminated = False
            self.waited = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float | None = None) -> int:
            self.waited = True
            return 0

    procs: list[Proc] = []

    def popen(cmd: list[str], *args, **kwargs) -> Proc:
        proc = Proc()
        procs.append(proc)
        return proc

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    player = MpvPlayer()
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="aaa")
    player.play("/var/lib/romini/library/helmet.mp3", position_sec=0.0, uid="bbb")

    assert procs[0].terminated is True
    assert procs[0].waited is True


def test_mpv_player_kills_the_previous_track_if_terminate_is_ignored(monkeypatch) -> None:
    class Proc:
        def __init__(self) -> None:
            self.killed = False

        def terminate(self) -> None:
            return

        def wait(self, timeout: float | None = None) -> int:
            if self.killed:
                return 0
            raise subprocess.TimeoutExpired(cmd="mpv", timeout=timeout or 0)

        def kill(self) -> None:
            self.killed = True

    procs: list[Proc] = []

    def popen(cmd: list[str], *args, **kwargs) -> Proc:
        proc = Proc()
        procs.append(proc)
        return proc

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", popen)
    player = MpvPlayer()
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="aaa")
    player.play("/var/lib/romini/library/helmet.mp3", position_sec=0.0, uid="bbb")

    assert procs[0].killed is True


def test_mpv_player_pause_terminates_the_running_track(monkeypatch) -> None:
    class Proc:
        def __init__(self) -> None:
            self.terminated = False

        def terminate(self) -> None:
            self.terminated = True

    proc = Proc()
    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", lambda *args, **kwargs: proc)
    player = MpvPlayer()
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="aaa")
    player.pause()

    assert proc.terminated is True
    assert player.is_playing() is False


def test_mpv_player_records_when_playback_started(monkeypatch) -> None:
    from datetime import datetime

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", lambda *args, **kwargs: object())
    player = MpvPlayer(clock=lambda: datetime(2026, 9, 19, 22, 33))
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04aabbcc")

    assert player.started_at() == datetime(2026, 9, 19, 22, 33)


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


def test_mpv_player_position_sec_reads_time_pos(monkeypatch) -> None:
    from romini.composition.pi import MpvPlayer

    monkeypatch.setattr("romini.composition.pi.subprocess.Popen", lambda *args, **kwargs: object())
    sent: list[bytes] = []

    class Sock:
        def sendall(self, data: bytes) -> None:
            sent.append(data)

        def recv(self, n: int) -> bytes:
            return b'{"data":74.2,"error":"success"}\n'

        def close(self) -> None:
            return

    player = MpvPlayer(connect=lambda path: Sock())
    player.play("/var/lib/romini/library/frog.mp3", position_sec=0.0, uid="04aabbcc")

    assert player.position_sec() == 74.2
    assert b"time-pos" in sent[0]


def test_pn532_hat_turns_the_rf_field_on_and_raises_type_a_gain() -> None:
    from romini.composition.pn532_hat import configure_pn532_rf

    class Reader:
        def __init__(self) -> None:
            self.calls: list[object] = []

        def SAM_configuration(self) -> None:
            self.calls.append("sam")

        def call_function(self, command: int, params: list[int] | None = None) -> bytes:
            self.calls.append((command, list(params or [])))
            return b""

    reader = Reader()
    configure_pn532_rf(reader)

    assert reader.calls[0] == "sam"
    assert reader.calls[1] == (0x32, [0x01, 0x01])
    assert reader.calls[2] == (0x32, [0x0A, 0x79, 0xF4, 0x3F, 0x11, 0x4D, 0x85, 0x61, 0x6F, 0x26, 0x62, 0x87])


def test_pn532_hat_exposes_pn532_spi() -> None:
    from romini.composition.pn532_hat import PN532_SPI

    assert callable(PN532_SPI)


def test_pn532_hat_uses_adafruit_spi() -> None:
    from pathlib import Path

    text = Path(__file__).with_name("pn532_hat.py").read_text()
    assert "adafruit_pn532.spi" in text
    assert "cs: int = 4" in text
    assert "adafruit_pn532.i2c" not in text
    assert "PN532_I2C" not in text
