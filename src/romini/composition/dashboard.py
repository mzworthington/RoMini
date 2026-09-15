from pathlib import Path
from shutil import disk_usage
from typing import Literal, Protocol

import yaml
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from romini.adapters.sqlite.settings import SqliteSettings
from romini.features.library.add_track import Catalog, Notices, Storage, add_track
from romini.features.library.assign import CatalogFile, confirm_assign
from romini.features.library.register_tag import name_tag
from romini.features.play_by_tag.place_figure import Mixer, PlayMode, on_volume_down, on_volume_set, on_volume_up

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def format_free_space(n: int) -> str:
    if n < 1024:
        return f"{n} bytes free"
    size = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit} free"
    return f"{n} bytes free"


class FigurePad(Protocol):
    def place(self, uid: str) -> None: ...


class RegisterMode(Protocol):
    assign_mode: bool


HOME_NOTICES = {
    "assigned": "Figure assigned",
    "play-mode": "Play mode saved",
    "uploaded": "Track stored",
    "full": "Storage is full",
    "register-on": "Place a figure on the box",
    "register-off": "Register off",
    "named": "Figure named",
    "presented": "Figure presented",
    "placed": "Figure placed",
    "needed": "Fill in the required fields",
    "volume": "Volume saved",
}


def _library_paths(storage: object) -> list[str]:
    listing = getattr(storage, "paths", None)
    if not callable(listing):
        return []
    return [str(path) for path in listing()]


class DiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def free_bytes(self) -> int:
        return int(disk_usage(self._root).free)

    def put(self, filename: str, audio: bytes) -> None:
        target = self._root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(audio)

    def paths(self) -> list[str]:
        files: list[str] = []
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            files.append(path.relative_to(self._root).as_posix())
        return files


def _notice_home(key: str) -> RedirectResponse:
    return RedirectResponse(f"/?notice={key}", status_code=303)


def _has_required(*values: str) -> bool:
    return all(value.strip() for value in values)


def create_dashboard(
    *,
    storage: Storage,
    notices: Notices | None = None,
    catalog: Catalog | None = None,
    assign_catalog: CatalogFile | None = None,
    settings: SqliteSettings | None = None,
    pad: FigurePad | None = None,
    register: RegisterMode | None = None,
    mixer: Mixer | None = None,
) -> FastAPI:
    app = FastAPI()

    def brand_asset(name: str) -> FileResponse:
        path = ASSETS_DIR / name
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/svg+xml")

    @app.get("/logo.svg")
    def logo() -> FileResponse:
        return brand_asset("logo.svg")

    @app.get("/favicon.svg")
    def favicon() -> FileResponse:
        return brand_asset("favicon.svg")

    @app.get("/mark.svg")
    def mark() -> FileResponse:
        return brand_asset("mark.svg")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        tracks: list[dict[str, str]] = []
        tags: list[dict[str, str]] = []
        if assign_catalog is not None:
            data = yaml.safe_load(assign_catalog.read_text()) or {}
            tracks = [
                {
                    "uid": str(track.get("uid") or ""),
                    "title": str(track.get("title") or ""),
                    "path": str(track.get("path") or ""),
                }
                for track in data.get("tracks") or []
                if str(track.get("uid") or "").strip()
                or str(track.get("title") or "").strip()
                or str(track.get("path") or "").strip()
            ]
            tags = [
                {"uid": str(tag.get("uid") or ""), "name": str(tag.get("name") or "")}
                for tag in data.get("tags") or []
                if str(tag.get("uid") or "").strip()
            ]
        play_mode = PlayMode.PRESENCE.value
        if settings is not None:
            remembered = settings.play_mode()
            if remembered is not None:
                play_mode = remembered.value
        notice_key = request.query_params.get("notice", "")
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "free_space": format_free_space(storage.free_bytes),
                "notice": HOME_NOTICES.get(notice_key, ""),
                "tracks": tracks,
                "tags": tags,
                "library_paths": _library_paths(storage),
                "play_mode": play_mode,
                "presence": PlayMode.PRESENCE.value,
                "tap": PlayMode.TAP.value,
                "pad": pad is not None,
                "register": register is not None,
                "assign_mode": bool(register.assign_mode) if register is not None else False,
                "poll": register is not None and register.assign_mode,
                "mixer": mixer is not None,
                "volume_level": mixer.level if mixer is not None else 0,
                "volume_ceiling": mixer.ceiling if mixer is not None else 100,
            },
        )

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": storage.free_bytes}

    @app.post("/tracks", response_model=None)
    async def upload_track(file: UploadFile | None = File(None)) -> RedirectResponse:
        class Quiet:
            def tell(self, message: str) -> None:
                return

        if file is None or not (file.filename or "").strip():
            return _notice_home("needed")
        audio = await file.read()
        stored = add_track(
            audio=audio,
            filename=file.filename or "track.bin",
            storage=storage,
            notices=notices if notices is not None else Quiet(),
            catalog=catalog,
        )
        notice = "uploaded" if stored else "full"
        return _notice_home(notice)

    class AssignBody(BaseModel):
        uid: str
        path: str
        title: str

    @app.post("/assign", response_model=None)
    async def assign_tag(request: Request) -> Response:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = AssignBody.model_validate(await request.json())
            if not _has_required(body.uid, body.path, body.title):
                raise HTTPException(status_code=422)
            confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)
            return Response(status_code=204)
        form = await request.form()
        body = AssignBody(uid=str(form["uid"]), path=str(form["path"]), title=str(form["title"]))
        if not _has_required(body.uid, body.path, body.title):
            return _notice_home("needed")
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)
        return _notice_home("assigned")

    class PlayModeBody(BaseModel):
        play_mode: PlayMode

    @app.put("/play-mode", status_code=204)
    def switch_play_mode(body: PlayModeBody) -> None:
        if settings is None:
            raise HTTPException(status_code=404)
        settings.remember_play_mode(body.play_mode)

    @app.post("/play-mode", response_model=None)
    async def switch_play_mode_form(request: Request) -> RedirectResponse:
        if settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        body = PlayModeBody.model_validate({"play_mode": str(form["play_mode"])})
        settings.remember_play_mode(body.play_mode)
        return _notice_home("play-mode")

    class VolumeBody(BaseModel):
        step: Literal["up", "down"] | None = None
        level: int | None = None

    @app.post("/volume", response_model=None)
    async def set_volume(request: Request) -> RedirectResponse:
        if mixer is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        payload: dict[str, object] = {}
        step = str(form.get("step") or "").strip()
        if step:
            payload["step"] = step
        raw_level = form.get("level")
        if raw_level is not None and str(raw_level).strip():
            payload["level"] = raw_level
        body = VolumeBody.model_validate(payload)
        if body.step == "up":
            on_volume_up(mixer=mixer)
        elif body.step == "down":
            on_volume_down(mixer=mixer)
        elif body.level is not None:
            on_volume_set(mixer=mixer, level=body.level)
        else:
            return _notice_home("needed")
        return _notice_home("volume")

    @app.post("/place/{uid}")
    def place_figure(uid: str) -> RedirectResponse:
        if pad is None:
            raise HTTPException(status_code=404)
        pad.place(uid)
        return _notice_home("placed")

    @app.post("/present")
    async def present_figure(request: Request) -> RedirectResponse:
        if pad is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        uid = str(form["uid"]).strip()
        if not uid:
            return _notice_home("needed")
        pad.place(uid)
        return _notice_home("presented")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        register.assign_mode = str(form.get("register")) == "on"
        notice = "register-on" if register.assign_mode else "register-off"
        return _notice_home(notice)

    @app.post("/tags/{uid}/name")
    async def name_registered_tag(uid: str, request: Request) -> RedirectResponse:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name_tag(uid=uid, name=str(form.get("name") or ""), catalog=assign_catalog)
        return _notice_home("named")

    return app


class PathCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read_text(self) -> str:
        return self._path.read_text()

    def write_text(self, text: str) -> None:
        self._path.write_text(text)


class DashboardListener:
    def __init__(self, server: object, thread: object, port: int) -> None:
        self._server = server
        self._thread = thread
        self.port = port

    def wait(self) -> None:
        self._thread.join()

    def close(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=2)


def start_dashboard(app: FastAPI, *, host: str, port: int) -> DashboardListener:
    from os import environ
    from threading import Thread
    from time import sleep

    import uvicorn

    if environ.get("ROMINI_PROFILE", "sim") == "sim" and host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dashboard binds localhost only")

    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        sleep(0.05)
    bound = port
    if server.servers:
        sock = server.servers[0].sockets[0]
        bound = int(sock.getsockname()[1])
    return DashboardListener(server, thread, bound)
