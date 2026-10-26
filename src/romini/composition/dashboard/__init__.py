from collections.abc import Callable
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from fastapi import FastAPI, Request

from romini.adapters.files.catalog import PathCatalog
from romini.adapters.files.storage import DiskStorage
from romini.composition.dashboard.ctx import DashboardCtx, DashboardDeps
from romini.composition.dashboard.responses import notice
from romini.composition.dashboard.server import DashboardListener, start_dashboard
from romini.composition.dashboard.templates_env import templates
from romini.features.audit.record import record_event
from romini.features.demo.policy import demo_forbids, demo_return_path
from romini.features.listening.log import sync_playback

from . import analytics as analytics_page
from . import backup as backup_page
from . import characters as characters_page
from . import figures, home, library
from . import settings as settings_page
from . import stories as stories_page

__all__ = [
    "DiskStorage",
    "PathCatalog",
    "DashboardListener",
    "create_dashboard",
    "start_dashboard",
    "templates",
]


def create_dashboard(deps: DashboardDeps | None = None, **extra: Any) -> FastAPI:
    if deps is not None and extra:
        raise TypeError("pass DashboardDeps or keywords")
    bound = deps if deps is not None else DashboardDeps(**extra)
    app = FastAPI(telemetry={"auto_configure": False})
    _install_guards(app, bound)
    ctx = _context(bound)
    home.mount(app, ctx)
    figures.mount(app, ctx)
    library.mount(app, ctx)
    stories_page.mount(app, ctx)
    characters_page.mount(app, ctx)
    settings_page.mount(app, ctx)
    backup_page.mount(app, ctx)
    analytics_page.mount(app, bound)
    return app


def _install_guards(app: FastAPI, deps: DashboardDeps) -> None:
    if deps.demo:
        _refuse_demo(app)
    if deps.traffic is not None:
        _note_traffic(app, deps.traffic)


def _refuse_demo(app: FastAPI) -> None:
    @app.middleware("http")
    async def refuse_demo_changes(request: Request, call_next: Callable) -> object:
        if demo_forbids(request.method, request.url.path):
            return notice(demo_return_path(request.headers.get("referer", "")), "demo")
        return await call_next(request)


def _note_traffic(app: FastAPI, traffic: object) -> None:
    @app.middleware("http")
    async def note_dashboard_traffic(_request: object, call_next: Callable) -> object:
        traffic.note(monotonic())
        return await call_next(_request)


def _context(deps: DashboardDeps) -> DashboardCtx:
    return DashboardCtx(
        storage=deps.storage,
        notices=deps.notices,
        catalog=deps.catalog,
        assign_catalog=deps.assign_catalog,
        settings=deps.settings,
        pad=deps.pad,
        register=deps.register,
        mixer=deps.mixer,
        battery=deps.battery,
        stories=deps.stories,
        covers=deps.covers,
        characters=deps.characters,
        secrets=deps.secrets,
        box_secrets=deps.box_secrets,
        drafter=deps.drafter,
        draft_post=deps.draft_post,
        speech=deps.speech,
        speak_post=deps.speak_post,
        player=deps.player,
        audit=deps.audit,
        update_status=deps.update_status,
        note=lambda action, summary, headline="": _note(deps, action, summary, headline=headline),
        note_failed=lambda action, label, err: _note_failed(deps, action, label, err),
        power=deps.power,
        updates=deps.updates,
        listening=deps.listening,
        mark_listening=lambda was_playing: _mark_listening(deps, was_playing),
        demo=deps.demo,
    )


def _note(deps: DashboardDeps, action: str, summary: str, *, headline: str = "") -> None:
    if deps.audit is None:
        return
    record_event(deps.audit, action=action, summary=summary, headline=headline, clock=lambda: datetime.now(UTC))


def _note_failed(deps: DashboardDeps, action: str, label: str, err: BaseException) -> None:
    code = getattr(err, "code", None)
    suffix = f" ({code})" if isinstance(code, int) else ""
    detail = str(getattr(err, "vendor_message", "") or "").strip()
    extra = f": {detail}" if detail else ""
    _note(deps, action, f"{label} failed{suffix}{extra}", headline=f"{label} failed")


def _mark_listening(deps: DashboardDeps, was_playing: bool) -> None:
    if deps.listening is None or deps.player is None:
        return
    sync_playback(
        deps.listening,
        was_playing=was_playing,
        is_playing=deps.player.is_playing(),
        at=datetime.now().astimezone(),
    )
