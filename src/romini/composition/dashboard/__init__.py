from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from fastapi import FastAPI

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.story_audio import Speech
from romini.features.audit.record import AuditLog, record_event
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage
from romini.features.library.assign import CatalogFile
from romini.features.listening.log import PlayLog, sync_playback
from romini.features.play_by_tag.now_playing import NowPlayingPlayer
from romini.features.play_by_tag.place_figure import Mixer
from romini.features.power.host import DashboardTraffic

from . import characters as characters_page
from . import figures, home, library
from . import settings as settings_page
from . import stories as stories_page
from .server import DashboardListener, start_dashboard
from .shared import (
    DashboardCtx,
    DiskStorage,
    FigurePad,
    PathCatalog,
    RegisterMode,
    ScriptDraft,
    templates,
)

__all__ = [
    "DiskStorage",
    "PathCatalog",
    "DashboardListener",
    "create_dashboard",
    "start_dashboard",
    "templates",
]


def create_dashboard(
    *,
    storage: Storage,
    notices: Notices | None = None,
    catalog: Catalog | None = None,
    assign_catalog: CatalogFile | None = None,
    settings: SqliteSettings | None = None,
    pad: FigurePad | None = None,
    register: RegisterMode | None = None,
    mixer: Mixer | None = None,
    battery: Battery | None = None,
    stories: Path | None = None,
    covers: Path | None = None,
    characters: Path | None = None,
    secrets: Path | None = None,
    box_secrets: Path | None = None,
    drafter: ScriptDraft | None = None,
    draft_post: Callable[..., bytes] | None = None,
    speech: Speech | None = None,
    speak_post: Callable[..., bytes] | None = None,
    player: NowPlayingPlayer | None = None,
    audit: AuditLog | None = None,
    listening: PlayLog | None = None,
    update_status: Path | None = None,
    power: object | None = None,
    updates: object | None = None,
    traffic: DashboardTraffic | None = None,
) -> FastAPI:
    app = FastAPI()
    if traffic is not None:

        @app.middleware("http")
        async def note_dashboard_traffic(_request: object, call_next: Callable) -> object:
            traffic.note(monotonic())
            return await call_next(_request)

    def note(action: str, summary: str, *, headline: str = "") -> None:
        if audit is None:
            return
        record_event(
            audit,
            action=action,
            summary=summary,
            headline=headline,
            clock=lambda: datetime.now(UTC),
        )

    def note_failed(action: str, label: str, err: BaseException) -> None:
        code = getattr(err, "code", None)
        suffix = f" ({code})" if isinstance(code, int) else ""
        detail = str(getattr(err, "vendor_message", "") or "").strip()
        extra = f": {detail}" if detail else ""
        note(action, f"{label} failed{suffix}{extra}", headline=f"{label} failed")

    def mark_listening(was_playing: bool) -> None:
        if listening is None or player is None:
            return
        sync_playback(
            listening,
            was_playing=was_playing,
            is_playing=player.is_playing(),
            at=datetime.now().astimezone(),
        )

    ctx = DashboardCtx(
        storage=storage,
        notices=notices,
        catalog=catalog,
        assign_catalog=assign_catalog,
        settings=settings,
        pad=pad,
        register=register,
        mixer=mixer,
        battery=battery,
        stories=stories,
        covers=covers,
        characters=characters,
        secrets=secrets,
        box_secrets=box_secrets,
        drafter=drafter,
        draft_post=draft_post,
        speech=speech,
        speak_post=speak_post,
        player=player,
        audit=audit,
        update_status=update_status,
        note=note,
        note_failed=note_failed,
        power=power,
        updates=updates,
        listening=listening,
        mark_listening=mark_listening,
    )
    home.mount(app, ctx)
    figures.mount(app, ctx)
    library.mount(app, ctx)
    stories_page.mount(app, ctx)
    characters_page.mount(app, ctx)
    settings_page.mount(app, ctx)
    return app
