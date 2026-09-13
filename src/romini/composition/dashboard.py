from pathlib import Path
from shutil import disk_usage

import yaml
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from romini.composition.sqlite_settings import SqliteSettings
from romini.features.library.add_track import Catalog, Notices, Storage, add_track
from romini.features.library.assign import CatalogFile, confirm_assign
from romini.features.play_by_tag.place_figure import PlayMode


class DiskStorage:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def free_bytes(self) -> int:
        return int(disk_usage(self._root).free)

    def put(self, filename: str, audio: bytes) -> None:
        (self._root / filename).write_bytes(audio)


def create_dashboard(
    *,
    storage: Storage,
    notices: Notices | None = None,
    catalog: Catalog | None = None,
    assign_catalog: CatalogFile | None = None,
    settings: SqliteSettings | None = None,
) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        rows = ""
        if assign_catalog is not None:
            data = yaml.safe_load(assign_catalog.read_text()) or {}
            for track in data.get("tracks") or []:
                rows += f"<li>{track.get('uid')} {track.get('title')}</li>"
        return (
            f"<p>free_bytes {storage.free_bytes}</p>"
            f"<ul>{rows}</ul>"
            '<form action="/tracks" method="post" enctype="multipart/form-data">'
            '<input type="file" name="file">'
            "<button>Upload</button>"
            "</form>"
            '<form action="/assign" method="post">'
            '<input name="uid">'
            '<input name="path">'
            '<input name="title">'
            "<button>Assign</button>"
            "</form>"
            '<form action="/play-mode" method="post">'
            '<input name="play_mode">'
            "<button>Set play mode</button>"
            "</form>"
        )

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": storage.free_bytes}

    @app.post("/tracks", status_code=201)
    async def upload_track(file: UploadFile = File()) -> dict[str, bool]:
        class Quiet:
            def tell(self, message: str) -> None:
                return

        audio = await file.read()
        stored = add_track(
            audio=audio,
            filename=file.filename or "track.bin",
            storage=storage,
            notices=notices if notices is not None else Quiet(),
            catalog=catalog,
        )
        return {"stored": stored}

    class AssignBody(BaseModel):
        uid: str
        path: str
        title: str

    @app.post("/assign", status_code=204)
    async def assign_tag(request: Request) -> None:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            body = AssignBody.model_validate(await request.json())
        else:
            form = await request.form()
            body = AssignBody(uid=str(form["uid"]), path=str(form["path"]), title=str(form["title"]))
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)

    class PlayModeBody(BaseModel):
        play_mode: PlayMode

    @app.put("/play-mode", status_code=204)
    def switch_play_mode(body: PlayModeBody) -> None:
        if settings is None:
            raise HTTPException(status_code=404)
        settings.remember_play_mode(body.play_mode)

    @app.post("/play-mode", status_code=204)
    async def switch_play_mode_form(request: Request) -> None:
        if settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        body = PlayModeBody.model_validate({"play_mode": str(form["play_mode"])})
        settings.remember_play_mode(body.play_mode)

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

    def close(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=2)


def start_dashboard(app: FastAPI, *, host: str, port: int) -> DashboardListener:
    from os import environ
    from threading import Thread
    from time import sleep

    import uvicorn

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dashboard binds localhost only")
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
