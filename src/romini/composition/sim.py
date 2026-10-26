import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from romini.adapters.sqlite.audit import SqliteAudit
from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.adapters.sqlite.mixer import SqliteMixer
from romini.adapters.sqlite.play_log import SqlitePlayLog
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
from romini.features.listening.log import sync_playback
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


@dataclass
class SimRig:
    catalog_yaml: str
    library_root: str
    audio_exists: Callable[[str], bool]
    player: Player
    led: StatusLed
    play_mode: PlayMode
    assign_mode: bool
    sessions: Sessions | None = None
    mixer: Mixer | None = None
    halt: Halt | None = None


class SimBox:
    def __init__(self, rig: SimRig | None = None, **parts: Any) -> None:
        if rig is not None and parts:
            raise TypeError("pass SimRig or keywords")
        bound = rig if rig is not None else SimRig(**parts)
        self.library = import_catalog(
            bound.catalog_yaml,
            library_root=bound.library_root,
            audio_exists=bound.audio_exists,
        )
        self.player = bound.player
        self.led = bound.led
        self.play_mode = bound.play_mode
        self.assign_mode = bound.assign_mode
        self.sessions = bound.sessions if bound.sessions is not None else MemorySessions()
        self.mixer = _live_mixer(bound.player, bound.mixer)
        self.halt = bound.halt if bound.halt is not None else LoggingHalt()

    def note(self, action: str, summary: str, *, headline: str = "") -> None:
        log = getattr(self, "audit", None)
        if log is None:
            return
        record_event(
            log,
            action=action,
            summary=summary,
            headline=headline,
            clock=lambda: datetime.now(UTC),
        )

    def close_listening(self) -> None:
        log = getattr(self, "listening", None)
        if log is None:
            return
        log.end(datetime.now().astimezone())

    def mark_listening(self, was_playing: bool) -> None:
        log = getattr(self, "listening", None)
        if log is None:
            return
        sync_playback(
            log,
            was_playing=was_playing,
            is_playing=self.player.is_playing(),
            at=datetime.now().astimezone(),
        )

    def place(self, uid: str) -> None:
        if getattr(self, "quiet", False) and not self.assign_mode:
            return
        beep, earcon = _beep(self)
        if self.assign_mode:
            _register_placed(self, uid, earcon)
            return
        _play_placed(self, uid, beep, earcon)

    def lift(self, uid: str, *, elapsed_sec: float, position_sec: float) -> None:
        if self.sessions is None:
            return
        was_playing = self.player.is_playing()
        on_figure_lifted(
            uid,
            play_mode=self.play_mode,
            elapsed_sec=elapsed_sec,
            position_sec=position_sec,
            player=self.player,
            sessions=self.sessions,
        )
        self.mark_listening(was_playing)
        self.note("lift", f"Lifted {uid}", headline="Tag lifted")


def _live_mixer(player: Player, mixer: Mixer | None) -> Mixer:
    chosen = mixer if mixer is not None else MemoryMixer()
    apply = getattr(player, "set_volume", None)
    if callable(apply):
        chosen = LiveMixer(chosen, apply)
    if hasattr(player, "mixer"):
        player.mixer = chosen
    return chosen


def _beep(box: SimBox) -> tuple[bool, object | None]:
    settings = getattr(box, "settings", None)
    beep = True if settings is None else settings.nfc_beep()
    earcon = getattr(box, "earcon", None) if beep else None
    return beep, earcon


def _register_placed(box: SimBox, uid: str, earcon: object | None) -> None:
    catalog = getattr(box, "catalog_file", None)
    if catalog is None:
        return
    register_tag(uid=uid, catalog=catalog, led=box.led, earcon=earcon)
    box.note("register", f"Registered {uid}", headline="Figure registered")


def _play_placed(box: SimBox, uid: str, beep: bool, earcon: object | None) -> None:
    was_playing = box.player.is_playing()
    on_figure_placed(
        uid,
        play_mode=box.play_mode,
        assign_mode=box.assign_mode,
        library=box.library,
        player=box.player,
        led=box.led,
        sessions=box.sessions,
        earcon=earcon,
        beep=beep,
    )
    box.mark_listening(was_playing)
    _note_place(box, uid)


def _note_place(box: SimBox, uid: str) -> None:
    if box.player.is_playing() and box.player.playing_uid() == uid:
        box.note("play", f"Played {box.player.playing_path()}", headline="Story playing")
        return
    selected = box.player.selected_track()
    if selected is not None and selected[0] == uid:
        box.note("select", f"Selected {uid}", headline="Figure selected")
        return
    if box.library.track_for(uid) is None:
        box.note("place", f"No story for {uid}", headline="No story linked")
        return
    box.note("place", f"Placed {uid}", headline="Figure placed")


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
    box.settings = settings
    box.audit = SqliteAudit(conn)
    box.listening = SqlitePlayLog(conn)
    return box


def load_sim_box_from_env(
    *,
    player: Player,
    led: StatusLed,
    sessions: Sessions | None = None,
) -> SimBox:
    profile = os.environ.get("ROMINI_PROFILE", "sim")
    if profile not in {"sim", "pi", "demo"}:
        raise ValueError(f"unsupported profile: {profile}")
    data = os.environ.get("ROMINI_DATA")
    if not data:
        raise ValueError("ROMINI_DATA is required")
    box = load_sim_box(data_dir=Path(data), player=player, led=led, sessions=sessions)
    if profile == "pi":
        box.halt = SystemdHalt()
    return box
