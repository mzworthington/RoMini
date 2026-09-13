from enum import StrEnum
from typing import Protocol


class PlayMode(StrEnum):
    PRESENCE = "presence"
    TAP = "tap"


class Library(Protocol):
    def track_for(self, uid: str) -> str | None: ...


class Player(Protocol):
    def play(self, path: str, *, position_sec: float, uid: str) -> None: ...

    def select(self, uid: str, path: str) -> None: ...

    def selected_track(self) -> tuple[str, str] | None: ...

    def pause(self) -> None: ...

    def stop(self) -> None: ...

    def is_playing(self) -> bool: ...

    def playing_uid(self) -> str | None: ...

    def playing_path(self) -> str | None: ...


class StatusLed(Protocol):
    def pulse(self) -> None: ...

    def flash(self) -> None: ...


class Sessions(Protocol):
    def remember(self, uid: str, position_sec: float) -> None: ...


class Mixer(Protocol):
    level: int
    ceiling: int

    def set_level(self, level: int) -> None: ...


class Halt(Protocol):
    def poweroff(self) -> None: ...


PRESENCE_LIFT_GRACE_SEC = 2.0
ASSIGN_IDLE_SEC = 60.0


def on_figure_placed(
    uid: str,
    *,
    play_mode: PlayMode,
    assign_mode: bool,
    library: Library,
    player: Player,
    led: StatusLed,
) -> None:
    if assign_mode:
        return
    path = library.track_for(uid)
    if path is None:
        return
    if play_mode is PlayMode.TAP:
        player.select(uid, path)
        return
    if play_mode is not PlayMode.PRESENCE:
        return
    if player.is_playing() and player.playing_uid() == uid:
        return
    if player.is_playing():
        player.stop()
    player.play(path, position_sec=0.0, uid=uid)
    led.pulse()


def on_figure_lifted(
    uid: str,
    *,
    play_mode: PlayMode,
    elapsed_sec: float,
    position_sec: float,
    player: Player,
    sessions: Sessions,
) -> None:
    if play_mode is not PlayMode.PRESENCE:
        return
    if elapsed_sec <= PRESENCE_LIFT_GRACE_SEC:
        return
    player.pause()
    sessions.remember(uid, position_sec)


def on_play_pressed(*, player: Player) -> None:
    if player.is_playing():
        player.pause()
        return
    selected = player.selected_track()
    if selected is None:
        return
    uid, path = selected
    player.play(path, position_sec=0.0, uid=uid)


def on_play_long_pressed(*, player: Player) -> None:
    uid = player.playing_uid()
    path = player.playing_path()
    if uid is None or path is None:
        return
    player.play(path, position_sec=0.0, uid=uid)


def on_volume_up(*, mixer: Mixer) -> None:
    if mixer.level >= mixer.ceiling:
        return
    mixer.set_level(mixer.level + 1)


def on_volume_down(*, mixer: Mixer) -> None:
    if mixer.level <= 0:
        return
    mixer.set_level(mixer.level - 1)


def on_track_ended(*, player: Player) -> None:
    player.stop()


def on_halt_pressed(
    *,
    player: Player,
    sessions: Sessions,
    led: StatusLed,
    halt: Halt,
    position_sec: float,
) -> None:
    if player.is_playing():
        uid = player.playing_uid()
        if uid is not None:
            sessions.remember(uid, position_sec)
    led.flash()
    halt.poweroff()


def next_assign_mode(*, assign_mode: bool, idle_sec: float) -> bool:
    if not assign_mode:
        return False
    return idle_sec < ASSIGN_IDLE_SEC
