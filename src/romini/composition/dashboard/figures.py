import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.covers import figure_cover_key, locate_track_cover, save_track_cover
from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.responses import notice
from romini.composition.dashboard.routing import mount_routes
from romini.features.library.register_tag import name_tag
from romini.features.stories.cover import with_tag_image


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/figures", ["GET"], figures_page, False, {"response_class": HTMLResponse}),
            ("/register-mode", ["POST"], switch_register_mode, False, {}),
            ("/tags/{uid}/name", ["POST"], name_registered_tag, False, {}),
            ("/figures/cover", ["POST"], upload_figure_picture, False, {"response_model": None}),
            ("/figures/cover/{uid}", ["GET"], figure_picture, False, {}),
        ],
    )


def figures_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    return ctx.page(request, "figures.html", page="figures", page_title="Figures & Tags")


async def switch_register_mode(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.register is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    ctx.register.assign_mode = str(form.get("register")) == "on"
    key = "register-on" if ctx.register.assign_mode else "register-off"
    label = "Register on" if ctx.register.assign_mode else "Register off"
    ctx.note("register", label, headline=label)
    return notice("/figures", key)


async def name_registered_tag(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.assign_catalog is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    uid = str(request.path_params["uid"])
    name = str(form.get("name") or "")
    name_tag(uid=uid, name=name, catalog=ctx.assign_catalog)
    ctx.note("name", f"Named {uid} {name}".strip(), headline="Figure named")
    return notice("/figures", "named")


async def upload_figure_picture(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.covers is None or ctx.assign_catalog is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    uid = str(form.get("uid") or "")
    info = await _figure_image(ctx, form, uid)
    if info is None:
        ctx.note("upload", "Image rejected")
        return notice("/figures", "image-needed")
    _write_tag_image(ctx, uid, info)
    ctx.note("upload", f"Stored picture for {uid}")
    return notice("/figures", "image")


def figure_picture(ctx: DashboardCtx, request: Request) -> FileResponse:
    if ctx.covers is None:
        raise HTTPException(status_code=404)
    uid = str(request.path_params["uid"])
    key = figure_cover_key(uid)
    located = locate_track_cover(ctx.covers, key) if key else None
    if located is None:
        raise HTTPException(status_code=404)
    file_path, media = located
    return FileResponse(file_path, media_type=media)


async def _figure_image(ctx: DashboardCtx, form: object, uid: str) -> object | None:
    key = figure_cover_key(uid)
    catalog = yaml.safe_load(ctx.assign_catalog.read_text()) or {}
    known = {str(tag.get("uid") or "") for tag in catalog.get("tags") or []}
    upload = form.get("image")
    payload = await upload.read() if hasattr(upload, "read") else b""
    if not key or uid not in known:
        return None
    return save_track_cover(ctx.covers, key, payload)


def _write_tag_image(ctx: DashboardCtx, uid: str, info: object) -> None:
    original = ctx.assign_catalog.read_text()
    updated = with_tag_image(original, uid=uid, info=info)
    if updated != original:
        ctx.assign_catalog.write_text(updated)
