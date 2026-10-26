from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.requests import ClientDisconnect

from romini.composition.dashboard.covers import remember_track_cover
from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.library_files import preview_track, track_cover, upload_track_cover
from romini.composition.dashboard.media import library_paths, remember_hidden_track
from romini.composition.dashboard.responses import QuietNotices, has_required, is_audio_track, notice
from romini.composition.dashboard.routing import mount_routes
from romini.features.library.add_track import add_track
from romini.features.library.assign import catalog_without_track, confirm_assign, rename_track
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode, on_figure_placed


class QuietLed:
    def pulse(self) -> None:
        return

    def flash(self) -> None:
        return


class AssignBody(BaseModel):
    uid: str
    path: str
    title: str


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/library", ["GET"], library_page, False, {"response_class": HTMLResponse}),
            ("/tracks", ["POST"], upload_track, False, {"response_model": None}),
            ("/assign", ["POST"], assign_tag, False, {"response_model": None}),
            ("/library/delete", ["POST"], delete_library_track, False, {"response_model": None}),
            ("/place/{uid}", ["POST"], place_figure, False, {}),
            ("/library/play/{uid}", ["POST"], play_library_track, False, {}),
            ("/library/stop", ["POST"], stop_library_track, True, {}),
            ("/library/cover", ["POST"], upload_track_cover, False, {"response_model": None}),
            ("/library/cover/{path:path}", ["GET"], track_cover, False, {"response_model": None}),
            ("/library/file/{path:path}", ["GET"], preview_track, False, {}),
        ],
    )


def library_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    return ctx.page(request, "library.html", page="library", page_title="Audio Library")


async def upload_track(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    form = await _form(request)
    if form is None:
        return RedirectResponse("/library", status_code=303)
    uploads = _named_uploads(form)
    if not uploads:
        return notice("/library", "needed")
    stored_any = await _store_uploads(ctx, uploads)
    return _upload_response(form, stored_any)


async def assign_tag(ctx: DashboardCtx, request: Request) -> Response:
    if ctx.assign_catalog is None:
        raise HTTPException(status_code=404)
    if "application/json" in request.headers.get("content-type", ""):
        return await _assign_json(ctx, request)
    return await _assign_form(ctx, request)


async def delete_library_track(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    form = await request.form()
    path = str(form.get("path") or "").strip()
    if not path or any(part == ".." for part in Path(path).parts):
        return notice("/library", "needed")
    hidden = _drop_track(ctx, path)
    if hidden:
        response = notice("/library", "deleted")
        remember_hidden_track(response, request, path)
        return response
    ctx.note("delete", f"Deleted {path}", headline="Track deleted")
    return notice("/library", "deleted")


def place_figure(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.pad is None:
        raise HTTPException(status_code=404)
    uid = str(request.path_params["uid"])
    ctx.pad.place(uid)
    ctx.note("place", f"Placed {uid}", headline="Figure placed")
    return notice("/library", "placed")


def play_library_track(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    uid = str(request.path_params["uid"])
    library = _placed_library(ctx)
    was_playing = ctx.player.is_playing()
    on_figure_placed(
        uid,
        play_mode=_remembered_mode(ctx),
        assign_mode=False,
        library=library,
        player=ctx.player,
        led=getattr(ctx.pad, "led", None) or QuietLed(),
        sessions=getattr(ctx.pad, "sessions", None),
    )
    ctx.mark_listening(was_playing)
    _note_library_play(ctx, uid)
    return notice("/library", "playing")


def stop_library_track(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.player is None:
        raise HTTPException(status_code=404)
    was_playing = ctx.player.is_playing()
    ctx.player.stop()
    ctx.mark_listening(was_playing)
    ctx.note("play", "Stopped", headline="Playback stopped")
    return notice("/library", "stopped")


async def _form(request: Request) -> object | None:
    try:
        return await request.form()
    except ClientDisconnect:
        return None


def _named_uploads(form: object) -> list[object]:
    return [item for item in form.getlist("file") if getattr(item, "filename", None) and str(item.filename).strip()]


async def _store_uploads(ctx: DashboardCtx, uploads: list[object]) -> bool:
    stored_any = False
    for item in uploads:
        stored = await _store_one(ctx, item)
        if stored is not None:
            stored_any = stored_any or stored
    return stored_any


async def _store_one(ctx: DashboardCtx, item: object) -> bool | None:
    filename = str(item.filename or "")
    if not is_audio_track(filename):
        return None
    stored = add_track(
        audio=await item.read(),
        filename=filename,
        storage=ctx.storage,
        notices=ctx.notices if ctx.notices is not None else QuietNotices(),
        catalog=ctx.catalog,
    )
    _note_upload(ctx, filename, stored)
    return stored


def _note_upload(ctx: DashboardCtx, filename: str, stored: bool) -> None:
    if stored:
        ctx.note("upload", f"Stored {filename}", headline="Track stored")
        return
    ctx.note("upload", f"Could not store {filename} (full)", headline="Track not stored")


def _upload_response(form: object, stored_any: bool) -> RedirectResponse:
    response = notice("/library", "uploaded" if stored_any else "full")
    if stored_any and str(form.get("bind") or "") == "1":
        response.headers["location"] = f"{response.headers['location']}&bind=1"
    return response


async def _assign_json(ctx: DashboardCtx, request: Request) -> Response:
    body = AssignBody.model_validate(await request.json())
    if not has_required(body.uid, body.path, body.title):
        raise HTTPException(status_code=422)
    _confirm(ctx, body)
    return Response(status_code=204)


async def _assign_form(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    form = await request.form()
    path = str(form.get("path") or "")
    title = str(form.get("title") or "")
    uid = str(form.get("uid") or "")
    if not has_required(path, title):
        return notice("/library", "needed")
    if not uid.strip():
        rename_track(path=path, title=title, catalog=ctx.assign_catalog)
        ctx.note("rename", f"Renamed {path} to {title}", headline="Title saved")
        return notice("/library", "retitled")
    _confirm(ctx, AssignBody(uid=uid, path=path, title=title))
    return notice("/library", "assigned")


def _confirm(ctx: DashboardCtx, body: AssignBody) -> None:
    confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=ctx.assign_catalog)
    remember_track_cover(ctx.covers, ctx.assign_catalog, body.path)
    ctx.note("assign", f"Assigned {body.title} to {body.uid}", headline="Story assigned")


def _drop_track(ctx: DashboardCtx, path: str) -> bool:
    if ctx.assign_catalog is None:
        _drop_file(ctx, path)
        return False
    try:
        _rewrite_catalog(ctx, path)
    except PermissionError:
        return True
    return False


def _rewrite_catalog(ctx: DashboardCtx, path: str) -> None:
    def change(text: str) -> str:
        _drop_file(ctx, path)
        return catalog_without_track(text, path)

    exclusive = getattr(ctx.assign_catalog, "exclusive", None)
    if callable(exclusive):
        exclusive(change)
        return
    ctx.assign_catalog.write_text(change(ctx.assign_catalog.read_text()))


def _drop_file(ctx: DashboardCtx, path: str) -> None:
    remove = getattr(ctx.storage, "delete", None)
    if path not in library_paths(ctx.storage) or not callable(remove):
        return
    try:
        remove(path)
    except PermissionError:
        return


def _placed_library(ctx: DashboardCtx) -> object:
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


def _remembered_mode(ctx: DashboardCtx) -> PlayMode:
    if ctx.settings is None:
        return PlayMode.PRESENCE
    return ctx.settings.play_mode() or PlayMode.PRESENCE


def _note_library_play(ctx: DashboardCtx, uid: str) -> None:
    if ctx.player.is_playing():
        ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
        return
    ctx.note("play", f"Played {uid}", headline="Story playing")
