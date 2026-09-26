from typing import Protocol

from romini.features.play_by_tag.place_figure import PlayMode

READY_EARCON_PATH = "romini/hello_romy.wav"
HALT_EARCON_PATH = "romini/halt.wav"


class EarconPlayer(Protocol):
    def play_earcon(self, path: str) -> None: ...


class BootLed(Protocol):
    def animate(self) -> None: ...

    def become_steady(self) -> None: ...


class Library(Protocol):
    def track_for(self, uid: str) -> str | None: ...


class SessionRecall(Protocol):
    def position_for(self, uid: str) -> float | None: ...


class StoryPlayer(Protocol):
    def play(self, path: str, *, position_sec: float, uid: str) -> None: ...


def on_power_restored(
    *,
    player: EarconPlayer,
    led: BootLed,
    figure_present: bool,
    play_mode: PlayMode | None = None,
    uid: str | None = None,
    library: Library | None = None,
    sessions: SessionRecall | None = None,
    story_player: StoryPlayer | None = None,
) -> None:
    led.animate()
    player.play_earcon(READY_EARCON_PATH)
    led.become_steady()
    if (
        not figure_present
        or play_mode is not PlayMode.PRESENCE
        or uid is None
        or library is None
        or sessions is None
        or story_player is None
    ):
        return
    path = library.track_for(uid)
    if path is None:
        return
    position = sessions.position_for(uid) or 0.0
    story_player.play(path, position_sec=position, uid=uid)
