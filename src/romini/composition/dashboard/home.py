from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.library import QuietLed
from romini.composition.dashboard.shared import ASSETS_DIR, DashboardCtx, dashboard_return, notice
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
    def brand_asset(name: str, media_type: str) -> FileResponse:
        path = ASSETS_DIR / name
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type=media_type)

    @app.get("/logo.svg")
    def logo() -> FileResponse:
        return brand_asset("logo.svg", "image/svg+xml")

    @app.get("/favicon.svg")
    def favicon() -> FileResponse:
        return brand_asset("favicon.svg", "image/svg+xml")

    @app.get("/mark.svg")
    def mark() -> FileResponse:
        return brand_asset("mark.svg", "image/svg+xml")

    @app.get("/plus-jakarta-sans.woff2")
    def plus_jakarta() -> FileResponse:
        return brand_asset("plus-jakarta-sans.woff2", "font/woff2")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return ctx.page(request, "home.html", page="home", page_title="Live Player")

    @app.get("/now-playing", response_class=HTMLResponse)
    def now_playing_deck(request: Request) -> HTMLResponse:
        return ctx.page(request, "deck.html", page="now-playing", page_title="")

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": ctx.storage.free_bytes}

    def play_catalog_neighbor(step: int) -> None:
        if ctx.player is None or ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        root = getattr(ctx.storage, "_root", None)
        if root is None:
            raise HTTPException(status_code=404)
        library = import_catalog(
            ctx.assign_catalog.read_text(),
            library_root=str(root),
            audio_exists=lambda rel: (root / rel).is_file(),
        )
        uids = list(library.tracks)
        if not uids:
            return
        current = ctx.player.playing_uid()
        if current not in uids:
            uid = uids[0] if step > 0 else uids[-1]
        else:
            uid = uids[(uids.index(current) + step) % len(uids)]
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

    @app.post("/play")
    async def toggle_play(request: Request) -> RedirectResponse:
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

    @app.post("/play/seek")
    async def seek_play(request: Request) -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        back = dashboard_return(form.get("return"), "/")
        try:
            progress = int(str(form.get("progress")))
        except (TypeError, ValueError):
            return RedirectResponse(back, status_code=303)
        path = ctx.player.playing_path()
        read = getattr(ctx.storage, "get", None)
        audio = read(path) if path and callable(read) else None
        facts = describe_audio(audio) if isinstance(audio, bytes) else None
        on_seek(
            player=ctx.player,
            progress=progress,
            duration_sec=facts.duration_sec if facts else 0,
        )
        return RedirectResponse(back, status_code=303)

    @app.post("/play/restart")
    async def restart_play(request: Request) -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        back = dashboard_return(form.get("return"), "/")
        was_playing = ctx.player.is_playing()
        on_play_long_pressed(player=ctx.player)
        ctx.mark_listening(was_playing)
        ctx.note("play", f"Restarted {ctx.player.playing_path()}", headline="Story restarted")
        return notice(back, "playing")

    @app.post("/play/previous")
    async def previous_track(request: Request) -> RedirectResponse:
        form = await request.form()
        play_catalog_neighbor(-1)
        if ctx.player is not None and ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
        return notice(dashboard_return(form.get("return"), "/"), "playing")

    @app.post("/play/next")
    async def next_track(request: Request) -> RedirectResponse:
        form = await request.form()
        play_catalog_neighbor(1)
        if ctx.player is not None and ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
        return notice(dashboard_return(form.get("return"), "/"), "playing")

    @app.post("/safety/eject")
    def stop_and_eject() -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        was_playing = ctx.player.is_playing()
        ctx.player.stop()
        ctx.mark_listening(was_playing)
        ctx.note("eject", "Playback stopped", headline="Stopped and ejected")
        return notice("/", "stopped")

    @app.post("/safety/beep")
    async def set_nfc_beep(request: Request) -> RedirectResponse:
        if ctx.settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        on = str(form.get("nfc_beep") or "") == "on"
        ctx.settings.remember_nfc_beep(on)
        ctx.note("beep", "NFC beep on" if on else "NFC beep off", headline="NFC beep changed")
        return notice("/settings", "beep")

    @app.post("/safety/sleep")
    async def arm_sleep(request: Request) -> RedirectResponse:
        if ctx.settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        if str(form.get("cancel") or "") == "1":
            ctx.settings.remember_sleep_at(None)
            ctx.note("sleep", "Bedtime cancelled", headline="Bedtime cancelled")
            return notice("/settings", "sleep-off")
        deadline = arm_bedtime(datetime.now().astimezone())
        ctx.settings.remember_sleep_at(deadline)
        ctx.note("sleep", "Sleep in 30 minutes", headline="Bedtime armed")
        return notice("/settings", "sleep")

    @app.post("/mute")
    def mute() -> RedirectResponse:
        if ctx.mixer is None:
            raise HTTPException(status_code=404)
        on_volume_set(mixer=ctx.mixer, level=0)
        ctx.note("volume", "Muted", headline="Volume muted")
        return notice("/", "muted")
