from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.packs import (
    character_name_taken,
    clear_current,
    current_pack,
    open_character_pack,
    write_character,
)
from romini.composition.dashboard.responses import notice
from romini.composition.dashboard.routing import mount_routes


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/characters", ["GET"], characters_page, False, {"response_model": None}),
            ("/characters/{slug}", ["GET"], character_page, False, {"response_class": HTMLResponse}),
            ("/characters", ["POST"], save_character, False, {"response_model": None}),
            ("/characters/open", ["POST"], open_character, False, {"response_model": None}),
            ("/characters/new", ["POST"], new_character, True, {"response_model": None}),
        ],
    )


def characters_page(ctx: DashboardCtx, request: Request) -> HTMLResponse | RedirectResponse:
    if ctx.characters is None:
        return ctx.page(request, "stories.html", page="characters", page_title="Story Studio")
    pack = current_pack(ctx.characters)
    if pack == ctx.characters:
        return ctx.page(request, "stories.html", page="characters", page_title="Story Studio")
    dest = f"/characters/{pack.name}"
    if request.url.query:
        dest = f"{dest}?{request.url.query}"
    return RedirectResponse(dest, status_code=303)


def character_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    if ctx.characters is None:
        raise HTTPException(status_code=404)
    slug = str(request.path_params["slug"])
    open_character_pack(ctx.characters, slug)
    if current_pack(ctx.characters) != ctx.characters / slug:
        raise HTTPException(status_code=404)
    return ctx.page(request, "stories.html", page="characters", page_title="Story Studio")


async def save_character(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.characters is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    name = str(form.get("name") or "")
    background = str(form.get("background") or "")
    slug = _clean_slug(str(form.get("slug") or "").strip())
    if not name.strip():
        return notice("/characters", "needed")
    if character_name_taken(ctx.characters, name=name, except_slug=slug):
        return notice("/characters", "character-taken")
    pack = write_character(ctx.characters, name=name, background=background, slug=slug)
    ctx.note("character", f"Saved character {name.strip() or 'untitled'}", headline="Character saved")
    dest = f"/characters/{pack.name}" if pack != ctx.characters else "/characters"
    return notice(dest, "character")


async def open_character(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.characters is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    slug = str(form.get("slug") or "").strip()
    open_character_pack(ctx.characters, slug)
    if slug:
        ctx.note("character", f"Opened character {slug}", headline="Character opened")
    return notice("/characters", "character")


def new_character(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.characters is None:
        raise HTTPException(status_code=404)
    clear_current(ctx.characters)
    return RedirectResponse("/characters?compose=1", status_code=303)


def _clean_slug(slug: str) -> str:
    if slug in {".", ".."} or "/" in slug or "\\" in slug:
        return ""
    return slug
