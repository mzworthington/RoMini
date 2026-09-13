from collections.abc import Callable

from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import (
    Player,
    PlayMode,
    Sessions,
    StatusLed,
    on_figure_lifted,
    on_figure_placed,
)


class SimBox:
    def __init__(
        self,
        *,
        catalog_yaml: str,
        library_root: str,
        audio_exists: Callable[[str], bool],
        player: Player,
        led: StatusLed,
        play_mode: PlayMode,
        assign_mode: bool,
        sessions: Sessions | None = None,
    ) -> None:
        self.library = import_catalog(
            catalog_yaml,
            library_root=library_root,
            audio_exists=audio_exists,
        )
        self.player = player
        self.led = led
        self.play_mode = play_mode
        self.assign_mode = assign_mode
        self.sessions = sessions

    def place(self, uid: str) -> None:
        on_figure_placed(
            uid,
            play_mode=self.play_mode,
            assign_mode=self.assign_mode,
            library=self.library,
            player=self.player,
            led=self.led,
        )

    def lift(self, uid: str, *, elapsed_sec: float, position_sec: float) -> None:
        if self.sessions is None:
            return
        on_figure_lifted(
            uid,
            play_mode=self.play_mode,
            elapsed_sec=elapsed_sec,
            position_sec=position_sec,
            player=self.player,
            sessions=self.sessions,
        )
