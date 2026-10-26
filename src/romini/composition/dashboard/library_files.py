from mimetypes import guess_type
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

from romini.composition.dashboard.covers import locate_track_cover, save_track_cover
from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.media import library_paths, public_https_url
from romini.composition.dashboard.responses import notice
from romini.features.stories.cover import with_track_image

_AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac"}


async def upload_track_cover(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.covers is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    path = str(form.get("path") or "")
    if path not in library_paths(ctx.storage):
        return notice("/library", "image-needed")
    info = await _saved_cover(ctx, form, path)
    if info is None:
        ctx.note("upload", "Image rejected")
        return notice("/library", "image-needed")
    _write_track_image(ctx, path, info)
    ctx.note("upload", f"Stored cover for {path}")
    return notice("/library", "image")


def track_cover(ctx: DashboardCtx, request: Request) -> FileResponse | RedirectResponse:
    path = str(request.path_params["path"])
    if path not in library_paths(ctx.storage):
        raise HTTPException(status_code=404)
    public = _public_cover(ctx, path)
    if public:
        return RedirectResponse(public, status_code=302)
    return _local_cover(ctx, path)


def preview_track(ctx: DashboardCtx, request: Request) -> Response:
    path = str(request.path_params["path"])
    if path not in library_paths(ctx.storage):
        raise HTTPException(status_code=404)
    url = public_https_url(ctx.storage, path)
    if url:
        return RedirectResponse(url, status_code=302)
    audio = _stored_audio(ctx, path)
    return Response(content=audio, media_type=_audio_type(path))


async def _saved_cover(ctx: DashboardCtx, form: object, path: str) -> object | None:
    upload = form.get("image")
    data = await upload.read() if hasattr(upload, "read") else b""
    return save_track_cover(ctx.covers, path, data)


def _write_track_image(ctx: DashboardCtx, path: str, info: object) -> None:
    if ctx.assign_catalog is None:
        return
    original = ctx.assign_catalog.read_text()
    updated = with_track_image(original, paths={path}, info=info)
    if updated != original:
        ctx.assign_catalog.write_text(updated)


def _public_cover(ctx: DashboardCtx, path: str) -> str:
    locate = getattr(ctx.storage, "cover_url", None)
    if not callable(locate):
        return ""
    url = locate(path)
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return ""


def _local_cover(ctx: DashboardCtx, path: str) -> FileResponse:
    if ctx.covers is None:
        raise HTTPException(status_code=404)
    located = locate_track_cover(ctx.covers, path)
    if located is None:
        raise HTTPException(status_code=404)
    file_path, media = located
    return FileResponse(file_path, media_type=media)


def _stored_audio(ctx: DashboardCtx, path: str) -> bytes:
    read = getattr(ctx.storage, "get", None)
    if not callable(read):
        raise HTTPException(status_code=404)
    audio = read(path)
    if audio is None:
        raise HTTPException(status_code=404)
    return audio


def _audio_type(path: str) -> str:
    media, _encoding = guess_type(path)
    if media is not None and media.startswith("audio/"):
        return media
    return _AUDIO_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")
