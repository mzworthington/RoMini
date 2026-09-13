import os
from collections.abc import Callable
from pathlib import Path

from romini.composition.halt import LoggingHalt
from romini.composition.mixer import MemoryMixer
from romini.composition.pi import SystemdHalt
from romini.composition.sessions import MemorySessions
from romini.composition.sqlite_catalog import SqliteCatalog
from romini.composition.sqlite_mixer import SqliteMixer
from romini.composition.sqlite_sessions import SqliteSessions
from romini.composition.sqlite_settings import SqliteSettings
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import (
    Halt,
    Mixer,
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
        mixer: Mixer | None = None,
        halt: Halt | None = None,
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
        self.sessions = sessions if sessions is not None else MemorySessions()
        self.mixer = mixer if mixer is not None else MemoryMixer()
        self.halt = halt if halt is not None else LoggingHalt()

    def place(self, uid: str) -> None:
        on_figure_placed(
            uid,
            play_mode=self.play_mode,
            assign_mode=self.assign_mode,
            library=self.library,
            player=self.player,
            led=self.led,
            sessions=self.sessions,
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


def load_sim_box(
    *,
    data_dir: Path,
    player: Player,
    led: StatusLed,
    play_mode: PlayMode | None = None,
    assign_mode: bool = False,
    sessions: Sessions | None = None,
    mixer: Mixer | None = None,
) -> SimBox:
    library_root = data_dir / "library"
    catalog_yaml = (data_dir / "catalog.yaml").read_text()
    db = data_dir / "state.sqlite"
    if sessions is None:
        sessions = SqliteSessions(db)
    if mixer is None:
        mixer = SqliteMixer(db)
    settings = SqliteSettings(db)
    if play_mode is None:
        play_mode = settings.play_mode() or PlayMode.PRESENCE
    else:
        settings.remember_play_mode(play_mode)
    box = SimBox(
        catalog_yaml=catalog_yaml,
        library_root=str(library_root),
        audio_exists=lambda rel: (library_root / rel).is_file(),
        player=player,
        led=led,
        play_mode=play_mode,
        assign_mode=assign_mode,
        sessions=sessions,
        mixer=mixer,
    )
    SqliteCatalog(db).replace_tracks(box.library.tracks)
    return box


def load_sim_box_from_env(
    *,
    player: Player,
    led: StatusLed,
    sessions: Sessions | None = None,
) -> SimBox:
    profile = os.environ.get("ROMINI_PROFILE", "sim")
    if profile not in {"sim", "pi"}:
        raise ValueError(f"unsupported profile: {profile}")
    data = os.environ.get("ROMINI_DATA")
    if not data:
        raise ValueError("ROMINI_DATA is required")
    box = load_sim_box(data_dir=Path(data), player=player, led=led, sessions=sessions)
    if profile == "pi":
        box.halt = SystemdHalt()
    return box
