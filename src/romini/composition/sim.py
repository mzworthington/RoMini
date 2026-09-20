import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from romini.adapters.sqlite.audit import SqliteAudit
from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.adapters.sqlite.mixer import SqliteMixer
from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.adapters.sqlite.sessions import SqliteSessions
from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.halt import LoggingHalt
from romini.composition.mixer import LiveMixer, MemoryMixer
from romini.composition.pi import SystemdHalt
from romini.composition.provision import ensure_data_tree
from romini.composition.sessions import MemorySessions
from romini.features.audit.record import record_event
from romini.features.library.import_catalog import import_catalog
from romini.features.library.register_tag import register_tag
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
        mixer = mixer if mixer is not None else MemoryMixer()
        apply = getattr(player, "set_volume", None)
        if callable(apply):
            mixer = LiveMixer(mixer, apply)
        self.mixer = mixer
        if hasattr(player, "mixer"):
            player.mixer = mixer
        self.halt = halt if halt is not None else LoggingHalt()

    def note(self, action: str, summary: str) -> None:
        log = getattr(self, "audit", None)
        if log is None:
            return
        record_event(log, action=action, summary=summary, clock=lambda: datetime.now(UTC))

    def place(self, uid: str) -> None:
        if self.assign_mode:
            catalog = getattr(self, "catalog_file", None)
            if catalog is not None:
                register_tag(
                    uid=uid,
                    catalog=catalog,
                    led=self.led,
                    earcon=getattr(self, "earcon", None),
                )
                self.note("register", f"Registered {uid}")
            return
        on_figure_placed(
            uid,
            play_mode=self.play_mode,
            assign_mode=self.assign_mode,
            library=self.library,
            player=self.player,
            led=self.led,
            sessions=self.sessions,
        )
        if self.player.is_playing() and self.player.playing_uid() == uid:
            self.note("play", f"Played {self.player.playing_path()}")
            return
        selected = self.player.selected_track()
        if selected is not None and selected[0] == uid:
            self.note("select", f"Selected {uid}")
            return
        if self.library.track_for(uid) is None:
            self.note("place", f"No story for {uid}")
            return
        self.note("place", f"Placed {uid}")

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
        self.note("lift", f"Lifted {uid}")


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
    ensure_data_tree(data_dir)
    catalog_yaml = (data_dir / "catalog.yaml").read_text()
    db = data_dir / "state.sqlite"
    conn = open_state(db)
    ensure_schema(conn)
    if sessions is None:
        sessions = SqliteSessions(conn)
    if mixer is None:
        mixer = SqliteMixer(conn)
    settings = SqliteSettings(conn)
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
    SqliteCatalog(conn).replace_tracks(box.library.tracks)
    box.state = conn
    box.catalog_file = data_dir / "catalog.yaml"
    box.earcon = player if hasattr(player, "play_earcon") else None
    box.audit = SqliteAudit(conn)
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
