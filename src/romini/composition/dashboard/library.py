from mimetypes import guess_type
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.requests import ClientDisconnect

from romini.composition.dashboard.shared import (
    DashboardCtx,
    has_required,
    is_audio_track,
    library_paths,
    locate_track_cover,
    notice,
    remember_track_cover,
    save_track_cover,
)
from romini.features.library.add_track import add_track
from romini.features.library.assign import confirm_assign
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode, on_figure_placed
from romini.features.stories.cover import with_track_image


class QuietLed:
    def pulse(self) -> None:
        return

    def flash(self) -> None:
        return


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/library", response_class=HTMLResponse)
    def library_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "library.html", page="library", page_title="Library")

    @app.post("/tracks", response_model=None)
    async def upload_track(request: Request) -> RedirectResponse:
        class Quiet:
            def tell(self, message: str) -> None:
                return

        try:
            form = await request.form()
        except ClientDisconnect:
            return RedirectResponse("/library", status_code=303)
        uploads = [
            item for item in form.getlist("file") if getattr(item, "filename", None) and str(item.filename).strip()
        ]
        if not uploads:
            return notice("/library", "needed")
        stored_any = False
        for item in uploads:
            filename = str(item.filename or "")
            if not is_audio_track(filename):
                continue
            audio = await item.read()
            stored = add_track(
                audio=audio,
                filename=filename,
                storage=ctx.storage,
                notices=ctx.notices if ctx.notices is not None else Quiet(),
                catalog=ctx.catalog,
            )
            if stored:
                ctx.note("upload", f"Stored {filename}", headline="Track stored")
            else:
                ctx.note("upload", f"Could not store {filename} (full)", headline="Track not stored")
            stored_any = stored_any or stored
        uploaded = "uploaded" if stored_any else "full"
        response = notice("/library", uploaded)
        if stored_any and str(form.get("bind") or "") == "1":
            response.headers["location"] = f"{response.headers['location']}&bind=1"
        return response

    class AssignBody(BaseModel):
        uid: str
        path: str
        title: str

    @app.post("/assign", response_model=None)
    async def assign_tag(request: Request) -> Response:
        if ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = AssignBody.model_validate(await request.json())
            if not has_required(body.uid, body.path, body.title):
                raise HTTPException(status_code=422)
            confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=ctx.assign_catalog)
            remember_track_cover(ctx.covers, ctx.assign_catalog, body.path)
            ctx.note("assign", f"Assigned {body.title} to {body.uid}", headline="Story assigned")
            return Response(status_code=204)
        form = await request.form()
        body = AssignBody(uid=str(form["uid"]), path=str(form["path"]), title=str(form["title"]))
        if not has_required(body.uid, body.path, body.title):
            return notice("/library", "needed")
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=ctx.assign_catalog)
        remember_track_cover(ctx.covers, ctx.assign_catalog, body.path)
        ctx.note("assign", f"Assigned {body.title} to {body.uid}", headline="Story assigned")
        return notice("/library", "assigned")

    @app.post("/place/{uid}")
    def place_figure(uid: str) -> RedirectResponse:
        if ctx.pad is None:
            raise HTTPException(status_code=404)
        ctx.pad.place(uid)
        ctx.note("place", f"Placed {uid}", headline="Figure placed")
        return notice("/library", "placed")

    @app.post("/library/play/{uid}")
    def play_library_track(uid: str) -> RedirectResponse:
        if ctx.player is None or ctx.assign_catalog is None:
            raise HTTPException(status_code=404)
        root = getattr(ctx.storage, "_root", None)
        if root is None:
            raise HTTPException(status_code=404)
        play_mode = PlayMode.PRESENCE
        if ctx.settings is not None:
            play_mode = ctx.settings.play_mode() or PlayMode.PRESENCE
        was_playing = ctx.player.is_playing()
        on_figure_placed(
            uid,
            play_mode=play_mode,
            assign_mode=False,
            library=import_catalog(
                ctx.assign_catalog.read_text(),
                library_root=str(root),
                audio_exists=lambda rel: (root / rel).is_file(),
            ),
            player=ctx.player,
            led=getattr(ctx.pad, "led", None) or QuietLed(),
            sessions=getattr(ctx.pad, "sessions", None),
        )
        ctx.mark_listening(was_playing)
        if ctx.player.is_playing():
            ctx.note("play", f"Played {ctx.player.playing_path()}", headline="Story playing")
        else:
            ctx.note("play", f"Played {uid}", headline="Story playing")
        return notice("/library", "playing")

    @app.post("/library/stop")
    def stop_library_track() -> RedirectResponse:
        if ctx.player is None:
            raise HTTPException(status_code=404)
        was_playing = ctx.player.is_playing()
        ctx.player.stop()
        ctx.mark_listening(was_playing)
        ctx.note("play", "Stopped", headline="Playback stopped")
        return notice("/library", "stopped")

    @app.post("/library/cover", response_model=None)
    async def upload_track_cover(request: Request) -> RedirectResponse:
        if ctx.covers is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        path = str(form.get("path") or "")
        if path not in library_paths(ctx.storage):
            return notice("/library", "image-needed")
        upload = form.get("image")
        data = await upload.read() if hasattr(upload, "read") else b""
        info = save_track_cover(ctx.covers, path, data)
        if info is None:
            ctx.note("upload", "Image rejected")
            return notice("/library", "image-needed")
        if ctx.assign_catalog is not None:
            original = ctx.assign_catalog.read_text()
            updated = with_track_image(original, paths={path}, info=info)
            if updated != original:
                ctx.assign_catalog.write_text(updated)
        ctx.note("upload", f"Stored cover for {path}")
        return notice("/library", "image")

    @app.get("/library/cover/{path:path}")
    def track_cover(path: str) -> FileResponse:
        if ctx.covers is None or path not in library_paths(ctx.storage):
            raise HTTPException(status_code=404)
        located = locate_track_cover(ctx.covers, path)
        if located is None:
            raise HTTPException(status_code=404)
        file_path, media = located
        return FileResponse(file_path, media_type=media)

    @app.get("/library/file/{path:path}")
    def preview_track(path: str) -> Response:
        if path not in library_paths(ctx.storage):
            raise HTTPException(status_code=404)
        read = getattr(ctx.storage, "get", None)
        if not callable(read):
            raise HTTPException(status_code=404)
        audio = read(path)
        if audio is None:
            raise HTTPException(status_code=404)
        media, _ = guess_type(path)
        suffix = Path(path).suffix.lower()
        if media is None or not media.startswith("audio/"):
            media = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac"}.get(
                suffix, "application/octet-stream"
            )
        return Response(content=audio, media_type=media)
