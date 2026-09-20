from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import (
    DashboardCtx,
    character_name_taken,
    clear_current,
    notice,
    open_character_pack,
    write_character,
)


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/characters", response_class=HTMLResponse)
    def characters_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "characters.html", page="characters", page_title="Characters")

    @app.post("/characters", response_model=None)
    async def save_character(request: Request) -> RedirectResponse:
        if ctx.characters is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name = str(form.get("name") or "")
        background = str(form.get("background") or "")
        slug = str(form.get("slug") or "").strip()
        if slug in {".", ".."} or "/" in slug or "\\" in slug:
            slug = ""
        if not name.strip():
            return notice("/characters", "needed")
        if character_name_taken(ctx.characters, name=name, except_slug=slug):
            return notice("/characters", "character-taken")
        write_character(ctx.characters, name=name, background=background, slug=slug)
        ctx.note("character", f"Saved character {name.strip() or 'untitled'}")
        return notice("/characters", "character")

    @app.post("/characters/open", response_model=None)
    async def open_character(request: Request) -> RedirectResponse:
        if ctx.characters is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        open_character_pack(ctx.characters, slug)
        if slug:
            ctx.note("character", f"Opened character {slug}")
        return notice("/characters", "character")

    @app.post("/characters/new", response_model=None)
    def new_character() -> RedirectResponse:
        if ctx.characters is None:
            raise HTTPException(status_code=404)
        clear_current(ctx.characters)
        return RedirectResponse("/characters", status_code=303)
