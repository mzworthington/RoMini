from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import ASSETS_DIR, DashboardCtx, notice
from romini.features.play_by_tag.place_figure import on_play_pressed


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

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": ctx.storage.free_bytes}

    @app.post("/play")
    def toggle_play() -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        on_play_pressed(player=ctx.player)
        if ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}")
            return notice("/", "playing")
        ctx.note("play", "Paused")
        return notice("/", "paused")
