from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import Request
from fastapi.responses import HTMLResponse

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard.power import BoxPower, BoxUpdate
from romini.composition.dashboard.view import render_page
from romini.composition.story_audio import Speech
from romini.features.audit.record import AuditLog
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage
from romini.features.library.assign import CatalogFile
from romini.features.listening.log import PlayLog
from romini.features.play_by_tag.now_playing import NowPlayingPlayer
from romini.features.play_by_tag.place_figure import Mixer
from romini.features.power.host import DashboardTraffic


class FigurePad(Protocol):
    def place(self, uid: str) -> None: ...


class RegisterMode(Protocol):
    assign_mode: bool


class ScriptDraft(Protocol):
    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
        duration_seconds: int = 10,
    ) -> str: ...


@dataclass
class DashboardDeps:
    storage: Storage
    notices: Notices | None = None
    catalog: Catalog | None = None
    assign_catalog: CatalogFile | None = None
    settings: SqliteSettings | None = None
    pad: FigurePad | None = None
    register: RegisterMode | None = None
    mixer: Mixer | None = None
    battery: Battery | None = None
    stories: Path | None = None
    covers: Path | None = None
    characters: Path | None = None
    secrets: Path | None = None
    box_secrets: Path | None = None
    drafter: ScriptDraft | None = None
    draft_post: Callable[..., bytes] | None = None
    speech: Speech | None = None
    speak_post: Callable[..., bytes] | None = None
    player: NowPlayingPlayer | None = None
    audit: AuditLog | None = None
    listening: PlayLog | None = None
    update_status: Path | None = None
    power: BoxPower | None = None
    updates: BoxUpdate | None = None
    traffic: DashboardTraffic | None = None
    demo: bool = False
    posthog_token: str = ""
    posthog_host: str = ""


@dataclass
class DashboardCtx:
    storage: Storage
    notices: Notices | None
    catalog: Catalog | None
    assign_catalog: CatalogFile | None
    settings: SqliteSettings | None
    pad: FigurePad | None
    register: RegisterMode | None
    mixer: Mixer | None
    battery: Battery | None
    stories: Path | None
    covers: Path | None
    characters: Path | None
    secrets: Path | None
    box_secrets: Path | None
    drafter: ScriptDraft | None
    draft_post: Callable[..., bytes] | None
    speech: Speech | None
    speak_post: Callable[..., bytes] | None
    player: NowPlayingPlayer | None
    audit: AuditLog | None
    update_status: Path | None
    note: Callable[..., None]
    note_failed: Callable[[str, str, BaseException], None]
    power: BoxPower | None = None
    updates: BoxUpdate | None = None
    listening: PlayLog | None = None
    mark_listening: Callable[[bool], None] = lambda _was_playing: None
    demo: bool = False
    flash: str = ""

    def page(self, request: Request, template: str, *, page: str, page_title: str) -> HTMLResponse:
        flash = self.flash
        self.flash = ""
        return render_page(
            request,
            template,
            page=page,
            page_title=page_title,
            source=self,
            flash=flash,
        )
