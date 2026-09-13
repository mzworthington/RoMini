from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path

from romini.__main__ import main, run
from romini.composition.nfc import FakeNfc


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
