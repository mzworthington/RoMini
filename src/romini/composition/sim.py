from collections.abc import Callable

from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import Player, PlayMode, StatusLed, on_figure_placed


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

    def place(self, uid: str) -> None:
        on_figure_placed(
            uid,
            play_mode=self.play_mode,
            assign_mode=self.assign_mode,
            library=self.library,
            player=self.player,
            led=self.led,
        )
