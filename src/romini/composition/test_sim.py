from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.composition.halt import LoggingHalt
from romini.composition.http import apply_sim_http, start_sim_http
from romini.composition.inject import apply_sim_line, run_sim_lines
from romini.composition.nfc import FakeNfc, poll_nfc
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

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)


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


@dataclass
class FakeMixer:
    level: int
    ceiling: int

    def set_level(self, level: int) -> None:
        self.level = level


def test_sim_line_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
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
    box.mixer = mixer

    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_line_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
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
    box.mixer = mixer

    apply_sim_line(box, "vol down")

    assert mixer.level == 9


@dataclass
class FakeHalt:
    poweroffs: int = 0

    def poweroff(self) -> None:
        self.poweroffs += 1


def test_sim_line_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
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
    box.halt = halt

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert led.flashes == 1
    assert halt.poweroffs == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_line_remove_pauses_after_grace() -> None:
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
    apply_sim_line(box, "remove")

    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_load_sim_box_vol_up_uses_mixer(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    mixer = FakeMixer(level=10, ceiling=100)
    player = FakePlayer()
    led = FakeLed()

    box = load_sim_box(data_dir=data, player=player, led=led, mixer=mixer)
    apply_sim_line(box, "vol up")

    assert mixer.level == 11


def test_sim_http_place_starts_the_track() -> None:
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

    status = apply_sim_http(box, "POST", "/place/04aabbccddeeff")

    assert status == 204
    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_http_remove_pauses_after_grace() -> None:
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

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/remove")

    assert status == 204
    assert player.pauses == 1
    assert sessions.positions == {"04aabbccddeeff": 0.0}


def test_sim_http_vol_up_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
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
        mixer=mixer,
    )

    status = apply_sim_http(box, "POST", "/vol/up")

    assert status == 204
    assert mixer.level == 11


def test_sim_http_vol_down_steps_the_mixer() -> None:
    player = FakePlayer()
    led = FakeLed()
    mixer = FakeMixer(level=10, ceiling=100)
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
        mixer=mixer,
    )

    status = apply_sim_http(box, "POST", "/vol/down")

    assert status == 204
    assert mixer.level == 9


def test_sim_http_halt_flashes_and_powers_off() -> None:
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()
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
    box.halt = halt

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/halt")

    assert status == 204
    assert led.flashes == 1
    assert halt.poweroffs == 1


def test_sim_halt_logs_instead_of_powering_off() -> None:
    halt = LoggingHalt()

    halt.poweroff()

    assert halt.logs == ["halt"]


def test_load_sim_box_halt_logs_by_default(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    box = load_sim_box(data_dir=data, player=player, led=led, sessions=sessions)
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "halt")

    assert box.halt.logs == ["halt"]


def test_sim_http_listen_place_starts_the_track(tmp_path: Path) -> None:
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
    listener = start_sim_http(box, host="127.0.0.1", port=0)
    try:
        status = listener.post("/place/04aabbccddeeff")
    finally:
        listener.close()

    assert status == 204
    assert player.plays == [(str(stories / "frog-prince.mp3"), 0.0)]


def test_sim_http_refuses_non_localhost(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="localhost"):
        start_sim_http(box, host="0.0.0.0", port=0)


def test_sim_http_refuses_pi_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    with pytest.raises(ValueError, match="sim"):
        start_sim_http(box, host="127.0.0.1", port=0)


def test_load_sim_box_remembers_lift_by_default(tmp_path: Path) -> None:
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
    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift")

    assert player.pauses == 1


def test_load_sim_box_vol_up_works_by_default(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    box = load_sim_box(data_dir=data, player=FakePlayer(), led=FakeLed())

    apply_sim_line(box, "vol up")

    assert box.mixer.level == 1


def test_sim_place_after_lift_resumes_remembered_position(tmp_path: Path) -> None:
    data = tmp_path / "romini"
    stories = data / "library" / "stories"
    stories.mkdir(parents=True)
    (stories / "frog-prince.mp3").write_bytes(b"id3")
    (data / "catalog.yaml").write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    box = load_sim_box(data_dir=data, player=player, led=FakeLed())

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "lift 14.5")
    apply_sim_line(box, "place 04aabbccddeeff")

    path = str(stories / "frog-prince.mp3")
    assert player.plays == [(path, 0.0), (path, 14.5)]


def test_sim_line_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
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
        led=FakeLed(),
        play_mode=PlayMode.TAP,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play")

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_http_play_starts_selected_tap_track() -> None:
    player = FakePlayer()
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
        led=FakeLed(),
        play_mode=PlayMode.TAP,
        assign_mode=False,
    )

    apply_sim_http(box, "POST", "/place/04aabbccddeeff")
    status = apply_sim_http(box, "POST", "/play")

    assert status == 204
    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_sim_line_play_long_restarts_the_track() -> None:
    player = FakePlayer()
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
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )

    apply_sim_line(box, "place 04aabbccddeeff")
    apply_sim_line(box, "play long")

    assert player.plays == [
        ("/var/lib/romini/library/stories/frog-prince.mp3", 0.0),
        ("/var/lib/romini/library/stories/frog-prince.mp3", 0.0),
    ]


def test_nfc_poll_places_when_uid_appears() -> None:
    player = FakePlayer()
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
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    nfc = FakeNfc(uid="04aabbccddeeff")

    poll_nfc(box, nfc)

    assert player.plays == [("/var/lib/romini/library/stories/frog-prince.mp3", 0.0)]


def test_nfc_poll_lifts_when_uid_disappears() -> None:
    player = FakePlayer()
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
        led=FakeLed(),
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
    )
    nfc = FakeNfc(uid="04aabbccddeeff")

    seen = poll_nfc(box, nfc)
    nfc.clear()
    poll_nfc(box, nfc, previous_uid=seen)

    assert player.pauses == 1
