from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.library import QuietLed
from romini.composition.dashboard.responses import ASSETS_DIR, dashboard_return, notice
from romini.composition.dashboard.routing import mount_routes
from romini.features.library.import_catalog import import_catalog
from romini.features.library.track_facts import describe_audio
from romini.features.play_by_tag.place_figure import (
    PlayMode,
    on_figure_placed,
    on_play_long_pressed,
    on_play_pressed,
    on_seek,
    on_volume_set,
)
from romini.features.safety.bedtime import arm_bedtime


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/logo.svg", ["GET"], logo, True, {}),
            ("/favicon.svg", ["GET"], favicon, True, {}),
            ("/mark.svg", ["GET"], mark, True, {}),
            ("/plus-jakarta-sans.woff2", ["GET"], plus_jakarta, True, {}),
            ("/", ["GET"], home_page, False, {"response_class": HTMLResponse}),
            ("/now-playing", ["GET"], now_playing_deck, False, {"response_class": HTMLResponse}),
            ("/storage", ["GET"], storage_info, True, {}),
            ("/play", ["POST"], toggle_play, False, {}),
            ("/play/seek", ["POST"], seek_play, False, {}),
            ("/play/restart", ["POST"], restart_play, False, {}),
            ("/play/previous", ["POST"], previous_track, False, {}),
            ("/play/next", ["POST"], next_track, False, {}),
            ("/safety/eject", ["POST"], stop_and_eject, True, {}),
            ("/safety/beep", ["POST"], set_nfc_beep, False, {}),
            ("/safety/sleep", ["POST"], arm_sleep, False, {}),
            ("/mute", ["POST"], mute, True, {}),
        ],
    )


def brand_asset(name: str, media_type: str) -> FileResponse:
    path = ASSETS_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type=media_type)


def logo(_ctx: DashboardCtx) -> FileResponse:
    return brand_asset("logo.svg", "image/svg+xml")


def favicon(_ctx: DashboardCtx) -> FileResponse:
    return brand_asset("favicon.svg", "image/svg+xml")


def mark(_ctx: DashboardCtx) -> FileResponse:
    return brand_asset("mark.svg", "image/svg+xml")


def plus_jakarta(_ctx: DashboardCtx) -> FileResponse:
    return brand_asset("plus-jakarta-sans.woff2", "font/woff2")


def home_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    return ctx.page(request, "home.html", page="home", page_title="Live Player")


def now_playing_deck(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    return ctx.page(request, "deck.html", page="now-playing", page_title="")


def storage_info(ctx: DashboardCtx) -> dict[str, int]:
    return {"free_bytes": ctx.storage.free_bytes}


def play_catalog_neighbor(ctx: DashboardCtx, step: int) -> None:
    library = _neighbor_library(ctx)
    uids = list(library.tracks)
    if not uids:
        return
    _play_uid(ctx, library, _neighbor_uid(uids, ctx.player.playing_uid(), step))


async def toggle_play(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.player is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    back = dashboard_return(form.get("return"), "/")
    was_playing = ctx.player.is_playing()
    on_play_pressed(player=ctx.player)
    ctx.mark_listening(was_playing)
    if ctx.player.is_playing():
        ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
        return notice(back, "playing")
    ctx.note("play", "Paused", headline="Playback paused")
    return notice(back, "paused")


async def seek_play(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.player is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    back = dashboard_return(form.get("return"), "/")
    progress = _progress(form.get("progress"))
    if progress is None:
        return RedirectResponse(back, status_code=303)
    on_seek(player=ctx.player, progress=progress, duration_sec=_duration(ctx))
    return RedirectResponse(back, status_code=303)


async def restart_play(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.player is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    was_playing = ctx.player.is_playing()
    on_play_long_pressed(player=ctx.player)
    ctx.mark_listening(was_playing)
    ctx.note("play", f"Restarted {ctx.player.playing_path()}", headline="Story restarted")
    return notice(dashboard_return(form.get("return"), "/"), "playing")


async def previous_track(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    return await _step_track(ctx, request, -1)


async def next_track(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    return await _step_track(ctx, request, 1)


def stop_and_eject(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.player is None:
        raise HTTPException(status_code=404)
    was_playing = ctx.player.is_playing()
    ctx.player.stop()
    ctx.mark_listening(was_playing)
    ctx.note("eject", "Playback stopped", headline="Stopped and ejected")
    return notice("/", "stopped")


async def set_nfc_beep(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.settings is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    on = str(form.get("nfc_beep") or "") == "on"
    ctx.settings.remember_nfc_beep(on)
    ctx.note("beep", "NFC beep on" if on else "NFC beep off", headline="NFC beep changed")
    return notice("/settings", "beep")


async def arm_sleep(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.settings is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    if str(form.get("cancel") or "") == "1":
        ctx.settings.remember_sleep_at(None)
        ctx.note("sleep", "Bedtime cancelled", headline="Bedtime cancelled")
        return notice("/settings", "sleep-off")
    ctx.settings.remember_sleep_at(arm_bedtime(datetime.now().astimezone()))
    ctx.note("sleep", "Sleep in 30 minutes", headline="Bedtime armed")
    return notice("/settings", "sleep")


def mute(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.mixer is None:
        raise HTTPException(status_code=404)
    on_volume_set(mixer=ctx.mixer, level=0)
    ctx.note("volume", "Muted", headline="Volume muted")
    return notice("/", "muted")


def _neighbor_library(ctx: DashboardCtx) -> object:
    if ctx.player is None or ctx.assign_catalog is None:
        raise HTTPException(status_code=404)
    root = getattr(ctx.storage, "_root", None)
    if root is None:
        raise HTTPException(status_code=404)
    return import_catalog(
        ctx.assign_catalog.read_text(),
        library_root=str(root),
        audio_exists=lambda rel: (root / rel).is_file(),
    )


def _neighbor_uid(uids: list[str], current: str | None, step: int) -> str:
    if current not in uids:
        if step > 0:
            return uids[0]
        return uids[-1]
    return uids[(uids.index(current) + step) % len(uids)]


def _play_uid(ctx: DashboardCtx, library: object, uid: str) -> None:
    play_mode = PlayMode.PRESENCE
    if ctx.settings is not None:
        play_mode = ctx.settings.play_mode() or PlayMode.PRESENCE
    was_playing = ctx.player.is_playing()
    on_figure_placed(
        uid,
        play_mode=play_mode,
        assign_mode=False,
        library=library,
        player=ctx.player,
        led=getattr(ctx.pad, "led", None) or QuietLed(),
        sessions=getattr(ctx.pad, "sessions", None),
    )
    ctx.mark_listening(was_playing)


def _progress(raw: object) -> int | None:
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def _duration(ctx: DashboardCtx) -> float:
    path = ctx.player.playing_path()
    read = getattr(ctx.storage, "get", None)
    audio = read(path) if path and callable(read) else None
    facts = describe_audio(audio) if isinstance(audio, bytes) else None
    if facts is None:
        return 0
    return facts.duration_sec


async def _step_track(ctx: DashboardCtx, request: Request, step: int) -> RedirectResponse:
    form = await request.form()
    play_catalog_neighbor(ctx, step)
    if ctx.player is not None and ctx.player.is_playing():
        ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
    return notice(dashboard_return(form.get("return"), "/"), "playing")
