from enum import StrEnum
from typing import Protocol


class PlayMode(StrEnum):
    PRESENCE = "presence"
    TAP = "tap"


class Library(Protocol):
    def track_for(self, uid: str) -> str | None: ...


class Player(Protocol):
    def play(self, path: str, *, position_sec: float) -> None: ...


class StatusLed(Protocol):
    def pulse(self) -> None: ...


def on_figure_placed(
    uid: str,
    *,
    play_mode: PlayMode,
    assign_mode: bool,
    library: Library,
    player: Player,
    led: StatusLed,
) -> None:
    if play_mode is not PlayMode.PRESENCE or assign_mode:
        return
    path = library.track_for(uid)
    if path is None:
        return
    player.play(path, position_sec=0.0)
    led.pulse()
