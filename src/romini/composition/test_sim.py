from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.composition.inject import apply_sim_line, run_sim_lines
from romini.composition.sim import SimBox, load_sim_box, load_sim_box_from_env
from romini.features.play_by_tag.place_figure import PlayMode


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


def test_sim_place_plays_mapped_catalog_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    box.place("04aabbccddeeff")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]
    assert led.pulses == 1


@dataclass
class FakeSessions:
    positions: dict[str, float] = field(default_factory=dict)

    def remember(self, uid: str, position_sec: float) -> None:
        self.positions[uid] = position_sec


def test_sim_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    box.place("04aabbccddeeff")
    box.lift("04aabbccddeeff", elapsed_sec=2.1, position_sec=14.5)

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 14.5}


def test_load_sim_box_from_romini_data(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led)
    box.place("04aabbccddeeff")

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_load_sim_box_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    box = load_sim_box_from_env(player=player, led=led)
    box.place("04aabbccddeeff")

    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_sim_line_place_starts_the_track() -> None:
    player = FakePlayer()
    led = FakeLed()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_line_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_lines_stop_at_quit() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    box = SimBox(
        catalog_yaml="""
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
""",
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
        player=player,
        led=led,
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        sessions=sessions,
    )

    run_sim_lines(box, ["place 04aabbccddeeff", "quit", "lift"])

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]
    assert player.pauses == 0
