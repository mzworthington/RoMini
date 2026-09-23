from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from romini.composition.dashboard.shared import (
    DashboardCtx,
    dashboard_return,
    elevenlabs_api_key,
    notice,
    write_studio_keys,
)
from romini.composition.update import record_update_check
from romini.features.play_by_tag.place_figure import PlayMode, on_volume_down, on_volume_set, on_volume_up


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "settings.html", page="settings", page_title="Settings")

    class PlayModeBody(BaseModel):
        play_mode: PlayMode

    @app.put("/play-mode", status_code=204)
    def switch_play_mode(body: PlayModeBody) -> None:
        if ctx.settings is None:
            raise HTTPException(status_code=404)
        ctx.settings.remember_play_mode(body.play_mode)
        ctx.note("play-mode", f"Play mode set to {body.play_mode.value}", headline="Play mode changed")

    @app.post("/play-mode", response_model=None)
    async def switch_play_mode_form(request: Request) -> RedirectResponse:
        if ctx.settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        body = PlayModeBody.model_validate({"play_mode": str(form["play_mode"])})
        ctx.settings.remember_play_mode(body.play_mode)
        ctx.note("play-mode", f"Play mode set to {body.play_mode.value}", headline="Play mode changed")
        return notice("/settings", "play-mode")

    class VolumeBody(BaseModel):
        step: Literal["up", "down"] | None = None
        level: int | None = None

    @app.post("/volume", response_model=None)
    async def set_volume(request: Request) -> RedirectResponse:
        if ctx.mixer is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        back = dashboard_return(form.get("return"), "/settings")
        payload: dict[str, object] = {}
        step = str(form.get("step") or "").strip()
        if step:
            payload["step"] = step
        raw_level = form.get("level")
        if raw_level is not None and str(raw_level).strip():
            payload["level"] = raw_level
        body = VolumeBody.model_validate(payload)
        if body.step == "up":
            on_volume_up(mixer=ctx.mixer)
        elif body.step == "down":
            on_volume_down(mixer=ctx.mixer)
        elif body.level is not None:
            on_volume_set(mixer=ctx.mixer, level=body.level)
        else:
            return notice(back, "needed")
        ctx.note("volume", f"Volume set to {ctx.mixer.level}", headline="Volume changed")
        return notice(back, "volume")

    @app.post("/keys", response_model=None)
    async def save_keys(request: Request) -> RedirectResponse:
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

    @app.post("/system/power", response_model=None)
    async def system_power(request: Request) -> RedirectResponse:
        if ctx.power is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        action = str(form.get("action") or "")
        back = dashboard_return(form.get("return"), "/settings")
        if action == "restart":
            ctx.power.restart()
            ctx.note("power", "Restart requested", headline="Restart requested")
        elif action == "reboot":
            ctx.power.reboot()
            ctx.note("power", "Reboot requested", headline="Reboot requested")
        elif action == "poweroff":
            ctx.power.poweroff()
            ctx.note("power", "Halt", headline="Halt requested")
        else:
            return notice(back, "needed")
        return notice(back, "power")

    @app.post("/system/update", response_model=None)
    def system_update() -> RedirectResponse:
        if ctx.updates is None:
            raise HTTPException(status_code=404)
        if ctx.update_status is not None:
            record_update_check(ctx.update_status, "checking", datetime.now())
        try:
            ctx.updates.check()
        except OSError:
            if ctx.update_status is not None:
                record_update_check(ctx.update_status, "failed", datetime.now())
            ctx.note("update", "The update did not finish", headline="Check failed")
            return notice("/settings", "update")
        ctx.note("update", "Update check started", headline="Update check started")
        return notice("/settings", "update")
