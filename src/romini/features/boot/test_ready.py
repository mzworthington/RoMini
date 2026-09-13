from dataclasses import dataclass, field

from romini.features.boot.ready import READY_EARCON_PATH, on_power_restored
from romini.features.play_by_tag.place_figure import PlayMode


@dataclass
class FakeEarconPlayer:
    plays: list[str] = field(default_factory=list)

    def play_earcon(self, path: str) -> None:
        self.plays.append(path)


@dataclass
class FakeBootLed:
    animated: bool = False
    steady: bool = False

    def animate(self) -> None:
        self.animated = True

    def become_steady(self) -> None:
        self.steady = True


@dataclass
class FakeLibrary:
    tracks: dict[str, str]

    def track_for(self, uid: str) -> str | None:
        return self.tracks.get(uid)


@dataclass
class FakeBootSessions:
    positions: dict[str, float] = field(default_factory=dict)

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)


@dataclass
class FakeStoryPlayer:
    plays: list[tuple[str, float]] = field(default_factory=list)

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        self.plays.append((path, position_sec))


def test_power_returns_with_no_figure_plays_ready_earcon() -> None:
    player = FakeEarconPlayer()
    led = FakeBootLed()

    on_power_restored(player=player, led=led, figure_present=False)

    assert led.animated is True
    assert player.plays == [READY_EARCON_PATH]
    assert led.steady is True


def test_power_returns_in_presence_resumes_mapped_figure() -> None:
    earcon = FakeEarconPlayer()
    led = FakeBootLed()
    story = FakeStoryPlayer()
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/library/bear.mp3"})
    sessions = FakeBootSessions(positions={"04AABBCC": 14.5})

    on_power_restored(
        player=earcon,
        led=led,
        figure_present=True,
        play_mode=PlayMode.PRESENCE,
        uid="04AABBCC",
        library=library,
        sessions=sessions,
        story_player=story,
    )

    assert earcon.plays == [READY_EARCON_PATH]
    assert story.plays == [("/var/lib/romini/library/bear.mp3", 14.5)]


def test_ready_wav_is_packaged() -> None:
    from importlib.resources import files

    wav = files("romini").joinpath("ready.wav")
    assert wav.is_file()
    assert wav.read_bytes()[:4] == b"RIFF"
