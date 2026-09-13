from dataclasses import dataclass, field

from romini.composition.sim import SimBox
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
