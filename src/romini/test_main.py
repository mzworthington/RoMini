from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from romini.__main__ import main, run
from romini.composition.nfc import FakeNfc
from romini.composition.pi import MpvPlayer


@dataclass
class FakePlayer:
    plays: list[tuple[str, float]] = field(default_factory=list)
    pauses: int = 0
    stops: int = 0
    selected: tuple[str, str] | None = None
    _playing: bool = False
    _uid: str | None = None
    _path: str | None = None

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        self.plays.append((path, position_sec))
        self._playing = True
        self._uid = uid
        self._path = path

    def select(self, uid: str, path: str) -> None:
        self.selected = (uid, path)

    def selected_track(self) -> tuple[str, str] | None:
        return self.selected

    def pause(self) -> None:
        self.pauses += 1
        self._playing = False

    def stop(self) -> None:
        self.stops += 1
        self._playing = False
        self._uid = None

    def is_playing(self) -> bool:
        return self._playing

    def playing_uid(self) -> str | None:
        return self._uid

    def playing_path(self) -> str | None:
        return self._path


@dataclass
class FakeLed:
    pulses: int = 0
    flashes: int = 0

    def pulse(self) -> None:
        self.pulses += 1

    def flash(self) -> None:
        self.flashes += 1


def test_romini_core_main_does_not_start_http_unless_port_set(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        assert getattr(box, "http", None) is None
        assert getattr(box, "dashboard", None) is None
    finally:
        http = getattr(box, "http", None)
        if http is not None:
            http.close()
        dashboard = getattr(box, "dashboard", None)
        if dashboard is not None:
            dashboard.close()


def test_romini_core_main_loads_sim_from_env(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    box = main(player=player, led=led)
    box.place("04aabbccddeeff")

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_main_runs_sim_lines(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    main(player=player, led=led, lines=["place 04aabbccddeeff", "quit"])

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_run_reads_stdin(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setattr(
        "romini.__main__.sys.stdin",
        StringIO("place 04aabbccddeeff\nquit\n"),
    )
    player = FakePlayer()
    led = FakeLed()

    run(player=player, led=led)

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_main_starts_sim_http(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    player = FakePlayer()
    led = FakeLed()

    box = main(player=player, led=led)
    try:
        status = box.http.post("/place/04aabbccddeeff")
    finally:
        box.http.close()

    assert status == 204
    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_starts_sim_http_before_stdin_lines(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    order: list[str] = []

    def start_http(box, *, host: str, port: int):
        order.append("http")

        class Listener:
            port = 0

            def close(self) -> None:
                return

        return Listener()

    def lines() -> object:
        order.append("lines")
        yield "quit"

    monkeypatch.setattr("romini.__main__.start_sim_http", start_http)
    main(player=FakePlayer(), led=FakeLed(), lines=lines())

    assert order == ["http", "lines"]


def test_romini_core_main_starts_dashboard(tmp_path: Path, monkeypatch) -> None:
    import json
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/storage") as resp:
            body = json.loads(resp.read().decode())
    finally:
        box.dashboard.close()

    assert "free_bytes" in body


def test_romini_core_dashboard_place_starts_the_track(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import Request, urlopen

    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    player = FakePlayer()

    box = main(player=player, led=FakeLed())
    try:
        req = Request(f"http://127.0.0.1:{box.dashboard.port}/place/04aabbccddeeff", method="POST", data=b"")
        with urlopen(req) as resp:
            status = resp.status
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert status == 200
    assert "Place" in body
    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_main_runs_nfc_ticks(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    main(
        player=player,
        led=led,
        nfc=FakeNfc(uid="04aabbccddeeff"),
        ticks=[None],
    )

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_main_runs_catalog_ticks(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    def ticks() -> object:
        yield None
        (data / "catalog.yaml").write_text("tracks: []\n")
        yield None

    box = main(player=player, led=led, catalog_ticks=ticks())
    box.place("04aabbccddeeff")

    assert player.plays == []


def test_romini_core_main_nfc_ticks_poll_catalog(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    player = FakePlayer()
    led = FakeLed()

    def ticks() -> object:
        yield None
        (data / "catalog.yaml").write_text("tracks: []\n")
        yield None

    box = main(player=player, led=led, nfc=FakeNfc(), ticks=ticks())
    box.place("04aabbccddeeff")

    assert player.plays == []


def test_romini_core_main_pi_profile_defaults_mpv_player(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    box = main(led=FakeLed())

    assert isinstance(box.player, MpvPlayer)


def test_romini_core_main_pi_dashboard_binds_lan(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")
    hosts: list[str] = []

    class Listener:
        port = 80

        def close(self) -> None:
            return

    def start(app, *, host: str, port: int) -> Listener:
        hosts.append(host)
        return Listener()

    monkeypatch.setattr("romini.__main__.start_dashboard", start)
    main(led=FakeLed())

    assert hosts == ["0.0.0.0"]


def test_romini_core_main_pi_defaults_gpio_led(tmp_path: Path, monkeypatch) -> None:
    from romini.composition.gpio import GpioLed

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")

    class Gpio:
        BCM = 11
        OUT = 0
        HIGH = 1
        LOW = 0

        def setmode(self, mode: int) -> None:
            return

        def setup(self, pin: int, mode: int) -> None:
            return

        def output(self, pin: int, value: int) -> None:
            return

    monkeypatch.setattr("romini.__main__.load_rpi_gpio", lambda: Gpio())
    box = main()

    assert isinstance(box.led, GpioLed)


def test_romini_core_entry_on_pi_runs_nfc_ticks(tmp_path: Path, monkeypatch) -> None:
    from romini.__main__ import entry
    from romini.composition.nfc import FakeNfc

    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    monkeypatch.setattr("romini.__main__.default_nfc", lambda: FakeNfc(uid="04aabbccddeeff"))
    monkeypatch.setattr("romini.__main__.default_ticks", lambda: [None])
    player = FakePlayer()

    entry(player=player, led=FakeLed())

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_romini_core_entry_keeps_serving_after_stdin_eof(tmp_path: Path, monkeypatch) -> None:
    from threading import Event, Thread
    from time import sleep

    from romini.__main__ import entry
    from romini.composition.http import start_sim_http

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_HTTP_PORT", "0")
    monkeypatch.setattr("romini.__main__.sys.stdin", StringIO(""))

    ready = Event()
    listeners: list = []

    def start(box, *, host: str, port: int):
        listener = start_sim_http(box, host=host, port=port)
        listeners.append(listener)
        ready.set()
        return listener

    monkeypatch.setattr("romini.__main__.start_sim_http", start)
    worker = Thread(target=lambda: entry(player=FakePlayer(), led=FakeLed()), daemon=True)
    worker.start()
    assert ready.wait(timeout=2)
    sleep(0.2)

    assert worker.is_alive()
    listeners[0].close()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_romini_core_dashboard_has_register_form(tmp_path: Path, monkeypatch) -> None:
    from urllib.request import urlopen

    data = tmp_path / "romini"
    (data / "library").mkdir(parents=True)
    (data / "catalog.yaml").write_text("tracks: []\n")
    monkeypatch.setenv("ROMINI_DATA", str(data))
    monkeypatch.setenv("ROMINI_PROFILE", "sim")
    monkeypatch.setenv("ROMINI_DASHBOARD_PORT", "0")

    box = main(player=FakePlayer(), led=FakeLed())
    try:
        with urlopen(f"http://127.0.0.1:{box.dashboard.port}/") as resp:
            body = resp.read().decode()
    finally:
        box.dashboard.close()

    assert 'action="/register-mode"' in body
