import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import (
    DashboardCtx,
    figure_cover_key,
    locate_track_cover,
    notice,
    save_track_cover,
)
from romini.features.library.register_tag import name_tag
from romini.features.stories.cover import with_tag_image


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/figures", response_class=HTMLResponse)
    def figures_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "figures.html", page="figures", page_title="Figures & Tags")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if ctx.register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        ctx.register.assign_mode = str(form.get("register")) == "on"
        key = "register-on" if ctx.register.assign_mode else "register-off"
        label = "Register on" if ctx.register.assign_mode else "Register off"
        ctx.note("register", label, headline=label)
        return notice("/figures", key)

    @app.post("/tags/{uid}/name")
    async def name_registered_tag(uid: str, request: Request) -> RedirectResponse:
        if ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name = str(form.get("name") or "")
        name_tag(uid=uid, name=name, catalog=ctx.assign_catalog)
        ctx.note("name", f"Named {uid} {name}".strip(), headline="Figure named")
        return notice("/figures", "named")

    @app.post("/figures/cover", response_model=None)
    async def upload_figure_picture(request: Request) -> RedirectResponse:
        if ctx.covers is None or ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        uid = str(form.get("uid") or "")
        key = figure_cover_key(uid)
        catalog = yaml.safe_load(ctx.assign_catalog.read_text()) or {}
        known = {str(tag.get("uid") or "") for tag in catalog.get("tags") or []}
        upload = form.get("image")
        payload = await upload.read() if hasattr(upload, "read") else b""
        info = save_track_cover(ctx.covers, key, payload) if key and uid in known else None
        if info is None:
            ctx.note("upload", "Image rejected")
            return notice("/figures", "image-needed")
        original = ctx.assign_catalog.read_text()
        updated = with_tag_image(original, uid=uid, info=info)
        if updated != original:
            ctx.assign_catalog.write_text(updated)
        ctx.note("upload", f"Stored picture for {uid}")
        return notice("/figures", "image")

    @app.get("/figures/cover/{uid}")
    def figure_picture(uid: str) -> FileResponse:
        if ctx.covers is None:
            raise HTTPException(status_code=404)
        key = figure_cover_key(uid)
        located = locate_track_cover(ctx.covers, key) if key else None
        if located is None:
            raise HTTPException(status_code=404)
        file_path, media = located
        return FileResponse(file_path, media_type=media)
