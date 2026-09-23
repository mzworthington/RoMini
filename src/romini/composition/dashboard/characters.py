from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import (
    DashboardCtx,
    character_name_taken,
    clear_current,
    current_pack,
    notice,
    open_character_pack,
    write_character,
)


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/characters", response_model=None)
    def characters_page(request: Request) -> HTMLResponse | RedirectResponse:
        if ctx.characters is not None:
            pack = current_pack(ctx.characters)
            if pack != ctx.characters:
                dest = f"/characters/{pack.name}"
                if request.url.query:
                    dest = f"{dest}?{request.url.query}"
                return RedirectResponse(dest, status_code=303)
        return ctx.page(request, "characters.html", page="characters", page_title="Characters")

    @app.get("/characters/{slug}", response_class=HTMLResponse)
    def character_page(request: Request, slug: str) -> HTMLResponse:
        if ctx.characters is None:
            raise HTTPException(status_code=404)
        open_character_pack(ctx.characters, slug)
        if current_pack(ctx.characters) != ctx.characters / slug:
            raise HTTPException(status_code=404)
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
        pack = write_character(ctx.characters, name=name, background=background, slug=slug)
        ctx.note("character", f"Saved character {name.strip() or 'untitled'}", headline="Character saved")
        dest = f"/characters/{pack.name}" if pack != ctx.characters else "/characters"
        return notice(dest, "character")

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
