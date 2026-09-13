from dataclasses import dataclass, field

from romini.features.play_by_tag.place_figure import PlayMode, on_figure_placed


@dataclass
class FakeLibrary:
    tracks: dict[str, str]

    def track_for(self, uid: str) -> str | None:
        return self.tracks.get(uid)


@dataclass
class FakePlayer:
    plays: list[tuple[str, float]] = field(default_factory=list)

    def play(self, path: str, *, position_sec: float) -> None:
        self.plays.append((path, position_sec))


@dataclass
class FakeLed:
    pulses: int = 0

    def pulse(self) -> None:
        self.pulses += 1


def test_mapped_figure_starts_the_story_in_presence_mode() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]
    assert led.pulses == 1
