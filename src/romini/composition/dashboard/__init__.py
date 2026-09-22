from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.story_audio import Speech
from romini.features.audit.record import AuditLog, record_event
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage
from romini.features.library.assign import CatalogFile
from romini.features.play_by_tag.now_playing import NowPlayingPlayer
from romini.features.play_by_tag.place_figure import Halt, Mixer

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
    characters: Path | None = None,
    secrets: Path | None = None,
    box_secrets: Path | None = None,
    drafter: ScriptDraft | None = None,
    draft_post: Callable[..., bytes] | None = None,
    speech: Speech | None = None,
    speak_post: Callable[..., bytes] | None = None,
    player: NowPlayingPlayer | None = None,
    audit: AuditLog | None = None,
    update_status: Path | None = None,
    halt: Halt | None = None,
) -> FastAPI:
    app = FastAPI()

    def note(action: str, summary: str) -> None:
        if audit is None:
            return
        record_event(audit, action=action, summary=summary, clock=lambda: datetime.now(UTC))

    def note_failed(action: str, label: str, err: BaseException) -> None:
        code = getattr(err, "code", None)
        suffix = f" ({code})" if isinstance(code, int) else ""
        detail = str(getattr(err, "vendor_message", "") or "").strip()
        extra = f": {detail}" if detail else ""
        note(action, f"{label} failed{suffix}{extra}")

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
        halt=halt,
        note=note,
        note_failed=note_failed,
    )
    home.mount(app, ctx)
    figures.mount(app, ctx)
    library.mount(app, ctx)
    stories_page.mount(app, ctx)
    characters_page.mount(app, ctx)
    settings_page.mount(app, ctx)
    return app
