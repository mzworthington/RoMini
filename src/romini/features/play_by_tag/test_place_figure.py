from dataclasses import dataclass, field

from romini.features.play_by_tag.place_figure import (
    PlayMode,
    next_assign_mode,
    on_figure_lifted,
    on_figure_placed,
    on_halt_pressed,
    on_play_long_pressed,
    on_play_pressed,
    on_track_ended,
    on_volume_down,
    on_volume_up,
)


@dataclass
class FakeLibrary:
    tracks: dict[str, str]

    def track_for(self, uid: str) -> str | None:
        return self.tracks.get(uid)


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


@dataclass
class FakeEarcon:
    plays: list[str] = field(default_factory=list)

    def play_earcon(self, path: str) -> None:
        self.plays.append(path)


@dataclass
class FakeSessions:
    positions: dict[str, float] = field(default_factory=dict)

    def remember(self, uid: str, position_sec: float) -> None:
        self.positions[uid] = position_sec

    def position_for(self, uid: str) -> float | None:
        return self.positions.get(uid)


@dataclass
class FakeMixer:
    level: int
    ceiling: int

    def set_level(self, level: int) -> None:
        self.level = level


@dataclass
class FakeHalt:
    poweroffs: int = 0

    def poweroff(self) -> None:
        self.poweroffs += 1


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


def test_tap_selects_the_track_without_starting_playback() -> None:
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

    assert player.plays == []
    assert player.selected == ("04AABBCC", "/var/lib/romini/tracks/bear.mp3")


def test_play_button_starts_the_selected_tap_track() -> None:
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
    on_play_pressed(player=player)
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
