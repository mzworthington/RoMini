from dataclasses import dataclass, field

from romini.fakes import FakeHalt, FakeLed, FakeMixer, FakePlayer, FakeSessions
from romini.features.play_by_tag.place_figure import (
    PlayMode,
    next_assign_mode,
    on_figure_lifted,
    on_figure_placed,
    on_halt_pressed,
    on_play_long_pressed,
    on_play_pressed,
    on_seek_relative,
    on_track_ended,
    on_volume_down,
    on_volume_set,
    on_volume_up,
)


@dataclass
class FakeLibrary:
    tracks: dict[str, str]

    def track_for(self, uid: str) -> str | None:
        return self.tracks.get(uid)


@dataclass
class FakeEarcon:
    plays: list[str] = field(default_factory=list)

    def play_earcon(self, path: str) -> None:
        self.plays.append(path)


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


def test_mapped_figure_plays_connect_earcon() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()
    earcon = FakeEarcon()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
        earcon=earcon,
    )

    assert earcon.plays == ["romini/connect.wav"]


def test_unmapped_figure_stays_silent() -> None:
    library = FakeLibrary(tracks={})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04UNMAPPED",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.plays == []
    assert led.pulses == 0


def test_assign_mode_does_not_start_a_story_until_confirm() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=True,
        library=library,
        player=player,
        led=led,
    )
    assert player.plays == []

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]


def test_lift_pauses_after_grace() -> None:
    player = FakePlayer()
    sessions = FakeSessions()

    on_figure_lifted(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        elapsed_sec=2.1,
        position_sec=14.5,
        player=player,
        sessions=sessions,
    )

    assert player.pauses == 1
    assert sessions.positions == {"04AABBCC": 14.5}


def test_different_figure_during_grace_stops_previous_track() -> None:
    library = FakeLibrary(
        tracks={
            "A": "/var/lib/romini/tracks/a.mp3",
            "B": "/var/lib/romini/tracks/b.mp3",
        }
    )
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "A",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_figure_placed(
        "B",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.stops == 1
    assert player.plays == [
        ("/var/lib/romini/tracks/a.mp3", 0.0),
        ("/var/lib/romini/tracks/b.mp3", 0.0),
    ]


def test_same_figure_returns_within_grace_does_not_restart() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_figure_lifted(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        elapsed_sec=1.0,
        position_sec=14.5,
        player=player,
        sessions=sessions,
    )
    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.stops == 0
    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]
    assert sessions.positions == {}


def test_figure_returns_after_grace_resumes_remembered_position() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
        sessions=sessions,
    )
    on_figure_lifted(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        elapsed_sec=2.1,
        position_sec=14.5,
        player=player,
        sessions=sessions,
    )
    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
        sessions=sessions,
    )

    assert player.plays == [
        ("/var/lib/romini/tracks/bear.mp3", 0.0),
        ("/var/lib/romini/tracks/bear.mp3", 14.5),
    ]


def test_tap_starts_the_story() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]
    assert player.is_playing() is True
    assert led.pulses == 1


def test_same_figure_tap_pauses_playback() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]
    assert player.pauses == 1
    assert player.is_playing() is False


def test_different_figure_tap_starts_that_story() -> None:
    library = FakeLibrary(
        tracks={
            "A": "/var/lib/romini/tracks/a.mp3",
            "B": "/var/lib/romini/tracks/b.mp3",
        }
    )
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "A",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_figure_placed(
        "B",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )

    assert player.stops == 1
    assert player.plays == [
        ("/var/lib/romini/tracks/a.mp3", 0.0),
        ("/var/lib/romini/tracks/b.mp3", 0.0),
    ]
    assert player.is_playing() is True


def test_play_button_pauses_after_tap_started_the_story() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_play_pressed(player=player)

    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]
    assert player.pauses == 1
    assert player.is_playing() is False


def test_lift_in_tap_does_not_pause_the_track() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_figure_lifted(
        "04AABBCC",
        play_mode=PlayMode.TAP,
        elapsed_sec=2.1,
        position_sec=14.5,
        player=player,
        sessions=sessions,
    )

    assert player.pauses == 0
    assert player.is_playing() is True
    assert sessions.positions == {}


def test_play_button_pauses_when_a_track_is_playing() -> None:
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
    on_play_pressed(player=player)

    assert player.pauses == 1
    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]


def test_play_button_resumes_after_pause_in_presence() -> None:
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
    on_play_pressed(player=player)
    on_play_pressed(player=player)

    assert player.pauses == 1
    assert player.is_playing() is True


def test_long_press_play_restarts_the_track() -> None:
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
    on_play_long_pressed(player=player)

    assert player.plays == [
        ("/var/lib/romini/tracks/bear.mp3", 0.0),
        ("/var/lib/romini/tracks/bear.mp3", 0.0),
    ]


def test_volume_up_never_exceeds_the_ceiling() -> None:
    mixer = FakeMixer(level=100, ceiling=100)

    on_volume_up(mixer=mixer)

    assert mixer.level == 100


def test_volume_down_never_goes_below_zero() -> None:
    mixer = FakeMixer(level=0, ceiling=100)

    on_volume_down(mixer=mixer)

    assert mixer.level == 0


def test_volume_set_clamps_to_the_ceiling() -> None:
    mixer = FakeMixer(level=10, ceiling=100)

    on_volume_set(mixer=mixer, level=140)

    assert mixer.level == 100


def test_volume_set_clamps_below_zero() -> None:
    mixer = FakeMixer(level=10, ceiling=100)

    on_volume_set(mixer=mixer, level=-4)

    assert mixer.level == 0


def test_volume_set_stores_the_level() -> None:
    mixer = FakeMixer(level=10, ceiling=100)

    on_volume_set(mixer=mixer, level=42)

    assert mixer.level == 42


def test_track_end_stops_and_does_not_restart() -> None:
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
    on_track_ended(player=player)

    assert player.stops == 1
    assert player.is_playing() is False
    assert player.plays == [("/var/lib/romini/tracks/bear.mp3", 0.0)]


def test_short_press_halt_remembers_position_and_powers_off() -> None:
    library = FakeLibrary(tracks={"04AABBCC": "/var/lib/romini/tracks/bear.mp3"})
    player = FakePlayer()
    led = FakeLed()
    sessions = FakeSessions()
    halt = FakeHalt()

    on_figure_placed(
        "04AABBCC",
        play_mode=PlayMode.PRESENCE,
        assign_mode=False,
        library=library,
        player=player,
        led=led,
    )
    on_halt_pressed(
        player=player,
        sessions=sessions,
        led=led,
        halt=halt,
        position_sec=14.5,
    )

    assert led.flashes == 1
    assert halt.poweroffs == 1
    assert sessions.positions == {"04AABBCC": 14.5}


def test_assign_ends_on_idle() -> None:
    assert next_assign_mode(assign_mode=True, idle_sec=60.0) is False


def test_seek_relative_replays_from_the_shifted_place() -> None:
    player = FakePlayer()
    player.play("/var/lib/romini/tracks/bear.mp3", position_sec=40.0, uid="04AABBCC")

    moved = on_seek_relative(player=player, delta_sec=-15)

    assert moved is True
    assert player.plays[-1] == ("/var/lib/romini/tracks/bear.mp3", 25.0)


def test_seek_relative_does_nothing_when_the_plate_is_empty() -> None:
    player = FakePlayer()

    assert on_seek_relative(player=player, delta_sec=15) is False
    assert player.plays == []
