from mimetypes import guess_type
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from romini.composition.dashboard.shared import DashboardCtx, has_required, is_audio_track, library_paths, notice
from romini.features.library.add_track import add_track
from romini.features.library.assign import confirm_assign


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/library", response_class=HTMLResponse)
    def library_page(request: Request) -> HTMLResponse:
        return ctx.page(request, "library.html", page="library", page_title="Library")

    @app.post("/tracks", response_model=None)
    async def upload_track(request: Request) -> RedirectResponse:
        class Quiet:
            def tell(self, message: str) -> None:
                return

        form = await request.form()
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
                ctx.note("upload", f"Stored {filename}")
            else:
                ctx.note("upload", f"Could not store {filename} (full)")
            stored_any = stored_any or stored
        uploaded = "uploaded" if stored_any else "full"
        return notice("/library", uploaded)

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
            ctx.note("assign", f"Assigned {body.title} to {body.uid}")
            return Response(status_code=204)
        form = await request.form()
        body = AssignBody(uid=str(form["uid"]), path=str(form["path"]), title=str(form["title"]))
        if not has_required(body.uid, body.path, body.title):
            return notice("/library", "needed")
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=ctx.assign_catalog)
        ctx.note("assign", f"Assigned {body.title} to {body.uid}")
        return notice("/library", "assigned")

    @app.post("/place/{uid}")
    def place_figure(uid: str) -> RedirectResponse:
        if ctx.pad is None:
            raise HTTPException(status_code=404)
        ctx.pad.place(uid)
        ctx.note("place", f"Placed {uid}")
        return notice("/library", "placed")

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
