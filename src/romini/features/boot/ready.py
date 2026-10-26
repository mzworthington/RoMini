from typing import Protocol

from romini.features.play_by_tag.place_figure import PlayMode

READY_EARCON_PATH = "romini/connect.mp3"
HALT_EARCON_PATH = "romini/disconnect.mp3"


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
    **resume: object,
) -> None:
    led.animate()
    player.play_earcon(READY_EARCON_PATH)
    led.become_steady()
    _resume_story(figure_present=figure_present, **resume)


def _resume_story(
    *,
    figure_present: bool,
    play_mode: PlayMode | None = None,
    uid: str | None = None,
    library: Library | None = None,
    sessions: SessionRecall | None = None,
    story_player: StoryPlayer | None = None,
) -> None:
    if not _can_resume(figure_present, play_mode, uid, library, sessions, story_player):
        return
    path = library.track_for(uid)
    if path is None:
        return
    story_player.play(path, position_sec=sessions.position_for(uid) or 0.0, uid=uid)


def _can_resume(
    figure_present: bool,
    play_mode: PlayMode | None,
    uid: str | None,
    library: Library | None,
    sessions: SessionRecall | None,
    story_player: StoryPlayer | None,
) -> bool:
    if not figure_present or play_mode is not PlayMode.PRESENCE:
        return False
    return uid is not None and library is not None and sessions is not None and story_player is not None
