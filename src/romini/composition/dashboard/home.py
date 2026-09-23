from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.library import QuietLed
from romini.composition.dashboard.shared import ASSETS_DIR, DashboardCtx, dashboard_return, notice
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import (
    PlayMode,
    on_figure_placed,
    on_play_long_pressed,
    on_play_pressed,
    on_volume_set,
)


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
        return ctx.page(request, "home.html", page="home", page_title="")

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
        on_figure_placed(
            uid,
            play_mode=play_mode,
            assign_mode=False,
            library=library,
            player=ctx.player,
            led=getattr(ctx.pad, "led", None) or QuietLed(),
            sessions=getattr(ctx.pad, "sessions", None),
        )

    @app.post("/play")
    async def toggle_play(request: Request) -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        back = dashboard_return(form.get("return"), "/")
        on_play_pressed(player=ctx.player)
        if ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}")
            return notice(back, "playing")
        ctx.note("play", "Paused")
        return notice(back, "paused")

    @app.post("/play/restart")
    async def restart_play(request: Request) -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        back = dashboard_return(form.get("return"), "/")
        on_play_long_pressed(player=ctx.player)
        ctx.note("play", f"Restarted {ctx.player.playing_path()}")
        return notice(back, "playing")

    @app.post("/play/previous")
    async def previous_track(request: Request) -> RedirectResponse:
        form = await request.form()
        play_catalog_neighbor(-1)
        if ctx.player is not None and ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}")
        return notice(dashboard_return(form.get("return"), "/"), "playing")

    @app.post("/play/next")
    async def next_track(request: Request) -> RedirectResponse:
        form = await request.form()
        play_catalog_neighbor(1)
        if ctx.player is not None and ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}")
        return notice(dashboard_return(form.get("return"), "/"), "playing")

    @app.post("/mute")
    def mute() -> RedirectResponse:
        if ctx.mixer is None:
            raise HTTPException(status_code=404)
        on_volume_set(mixer=ctx.mixer, level=0)
        ctx.note("volume", "Muted")
        return notice("/", "muted")
