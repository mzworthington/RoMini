from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.responses import dashboard_return, notice
from romini.composition.dashboard.routing import mount_routes
from romini.composition.dashboard.studio_keys import elevenlabs_api_key, write_studio_keys
from romini.composition.update import record_update_check
from romini.features.play_by_tag.place_figure import PlayMode, on_volume_down, on_volume_set, on_volume_up

_POWER = {
    "restart": ("restart", "Restart requested", "Restart requested"),
    "reboot": ("reboot", "Reboot requested", "Reboot requested"),
    "poweroff": ("poweroff", "Halt", "Halt requested"),
}


class PlayModeBody(BaseModel):
    play_mode: PlayMode


class VolumeBody(BaseModel):
    step: Literal["up", "down"] | None = None
    level: int | None = None


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/settings", ["GET"], settings_page, False, {"response_class": HTMLResponse}),
            ("/play-mode", ["PUT"], switch_play_mode, False, {"status_code": 204, "response_model": None}),
            ("/play-mode", ["POST"], switch_play_mode_form, False, {"response_model": None}),
            ("/volume", ["POST"], set_volume, False, {"response_model": None}),
            ("/keys", ["POST"], save_keys, False, {"response_model": None}),
            ("/system/power", ["POST"], system_power, False, {"response_model": None}),
            ("/system/update", ["POST"], system_update, True, {"response_model": None}),
        ],
    )


def settings_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    return ctx.page(request, "settings.html", page="settings", page_title="System & Hardware")


async def switch_play_mode(ctx: DashboardCtx, request: Request) -> None:
    if ctx.settings is None:
        raise HTTPException(status_code=404)
    body = PlayModeBody.model_validate(await request.json())
    _remember_mode(ctx, body.play_mode)


async def switch_play_mode_form(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.settings is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    body = PlayModeBody.model_validate({"play_mode": str(form["play_mode"])})
    _remember_mode(ctx, body.play_mode)
    return notice("/settings", "play-mode")


async def set_volume(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.mixer is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    back = dashboard_return(form.get("return"), "/settings")
    body = VolumeBody.model_validate(_volume_payload(form))
    if not _apply_volume(ctx, body):
        return notice(back, "needed")
    ctx.note("volume", f"Volume set to {ctx.mixer.level}", headline="Volume changed")
    return notice(back, "volume")


async def save_keys(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.secrets is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    elevenlabs_key = str(form.get("elevenlabs_key") or "")
    write_studio_keys(
        ctx.secrets,
        gemini_key=str(form.get("gemini_key") or ""),
        elevenlabs_key=elevenlabs_key,
        elevenlabs_voices=str(form.get("elevenlabs_voices") or ""),
    )
    if elevenlabs_key.strip() and not elevenlabs_api_key(elevenlabs_key):
        ctx.note("keys", "Studio keys not saved (ElevenLabs key ID)", headline="Studio keys not saved")
        return notice("/settings", "speak-key-id")
    ctx.note("keys", "Saved studio keys", headline="Studio keys saved")
    return notice("/settings", "keys")


async def system_power(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.power is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    back = dashboard_return(form.get("return"), "/settings")
    chosen = _POWER.get(str(form.get("action") or ""))
    if chosen is None:
        return notice(back, "needed")
    method, summary, headline = chosen
    getattr(ctx.power, method)()
    ctx.note("power", summary, headline=headline)
    return notice(back, "power")


def system_update(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.updates is None:
        raise HTTPException(status_code=404)
    _mark_checking(ctx)
    try:
        ctx.updates.check()
    except OSError:
        return _update_failed(ctx)
    ctx.note("update", "Update check started", headline="Update check started")
    return notice("/settings", "update")


def _remember_mode(ctx: DashboardCtx, play_mode: PlayMode) -> None:
    ctx.settings.remember_play_mode(play_mode)
    ctx.note("play-mode", f"Play mode set to {play_mode.value}", headline="Play mode changed")


def _volume_payload(form: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    step = str(form.get("step") or "").strip()
    if step:
        payload["step"] = step
    raw_level = form.get("level")
    if raw_level is not None and str(raw_level).strip():
        payload["level"] = raw_level
    return payload


def _apply_volume(ctx: DashboardCtx, body: VolumeBody) -> bool:
    if body.step == "up":
        on_volume_up(mixer=ctx.mixer)
        return True
    if body.step == "down":
        on_volume_down(mixer=ctx.mixer)
        return True
    if body.level is not None:
        on_volume_set(mixer=ctx.mixer, level=body.level)
        return True
    return False


def _mark_checking(ctx: DashboardCtx) -> None:
    if ctx.update_status is not None:
        record_update_check(ctx.update_status, "checking", datetime.now())


def _update_failed(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.update_status is not None:
        record_update_check(ctx.update_status, "failed", datetime.now())
    ctx.note("update", "The update did not finish", headline="Check failed")
    return notice("/settings", "update")
