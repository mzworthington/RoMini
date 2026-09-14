from html import escape
from pathlib import Path
from shutil import disk_usage
from typing import Protocol

import yaml
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel

from romini.adapters.sqlite.settings import SqliteSettings
from romini.features.library.add_track import Catalog, Notices, Storage, add_track
from romini.features.library.assign import CatalogFile, confirm_assign
from romini.features.library.register_tag import name_tag
from romini.features.play_by_tag.place_figure import PlayMode

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONTS_HREF = (
    "https://fonts.googleapis.com/css2?family=Nunito:wght@700;900"
    "&amp;family=Quicksand:wght@500;600;700&amp;display=swap"
)

DASHBOARD_STYLE = """
:root {
  --story-coral: #FF6B6B;
  --magic-ochre: #F7B731;
  --olive-sun: #E5B887;
  --warm-chestnut: #4A2E18;
  --midnight-navy: #1E293B;
  --cloud-foam: #F8FAFC;
  color-scheme: light;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 600 1.125rem/1.45 Quicksand, system-ui, sans-serif;
  color: var(--midnight-navy);
  background:
    radial-gradient(900px 420px at 50% -80px, #FFF7ED 0%, transparent 70%),
    var(--cloud-foam);
}
main { max-width: 42rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }
.masthead {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0 0 1.25rem;
}
.mark {
  width: 7rem;
  height: 7rem;
  object-fit: cover;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  flex-shrink: 0;
}
h1, h2, caption {
  font-family: Nunito, Comfortaa, system-ui, sans-serif;
}
h1 {
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: 0.02em;
  margin: 0;
}
h1 span { color: #FF5252; }
.tag {
  margin: 0.15rem 0 0;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: #94A3B8;
}
.lede { color: #64748B; margin: 0.45rem 0 0; font-weight: 600; }
section {
  margin: 0 0 1.5rem;
  padding: 1.1rem 1.15rem;
  background: #FFFFFF;
  border: 1px solid #F1F5F9;
  border-radius: 1rem;
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.04);
  overflow-x: auto;
}
@media (max-width: 40rem) {
  .masthead { align-items: flex-start; }
  .mark { width: 5.5rem; height: 5.5rem; }
  th, td { padding: 0.4rem 0.3rem; }
}
h2 { font-size: 1.05rem; font-weight: 800; margin: 0 0 0.75rem; }
label { display: block; font-weight: 700; margin: 0.7rem 0 0.3rem; }
input, select, button { font: inherit; }
input[type="text"], input[type="file"], select {
  width: 100%;
  min-height: 2.75rem;
  padding: 0.4rem 0.6rem;
  border: 1px solid #E2E8F0;
  border-radius: 0.65rem;
  background: #fff;
  color: var(--midnight-navy);
}
button {
  min-height: 2.75rem;
  margin-top: 0.85rem;
  padding: 0.4rem 0.9rem;
  border: 0;
  border-radius: 0.65rem;
  background: var(--story-coral);
  color: #fff;
  font-weight: 700;
}
button:hover { filter: brightness(0.96); }
:focus-visible {
  outline: 3px solid var(--magic-ochre);
  outline-offset: 2px;
}
table { width: 100%; border-collapse: collapse; font-size: 1rem; position: relative; }
th, td { text-align: left; padding: 0.45rem 0.35rem; border-bottom: 1px solid #F1F5F9; vertical-align: middle; }
th { color: #64748B; font-weight: 700; }
caption {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
td form { margin: 0; }
td button { margin: 0; min-height: 2.25rem; }
.empty, .hint { color: #64748B; margin: 0.4rem 0 0; font-weight: 500; }
.hint { font-size: 0.95rem; }
.status {
  margin: 0 0 1.25rem;
  padding: 0.65rem 0.8rem;
  background: #FFF7ED;
  border-radius: 0.65rem;
  border-left: 4px solid var(--magic-ochre);
  font-weight: 700;
}
"""


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
}


def _library_paths(storage: object) -> list[str]:
    listing = getattr(storage, "paths", None)
    if not callable(listing):
        return []
    return [str(path) for path in listing()]


def _catalog_row(track: dict[str, object], *, pad: FigurePad | None) -> str:
    uid = escape(str(track.get("uid") or ""))
    title = escape(str(track.get("title") or ""))
    path = escape(str(track.get("path") or ""))
    place = ""
    if pad is not None:
        place = f'<td><form action="/place/{uid}" method="post"><button>Place</button></form></td>'
    return f"<tr><td>{uid}</td><td>{title}</td><td>{path}</td>{place}</tr>"


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
    def home(request: Request) -> str:
        tracks: list[dict] = []
        tags: list[dict] = []
        if assign_catalog is not None:
            data = yaml.safe_load(assign_catalog.read_text()) or {}
            tracks = [
                track
                for track in data.get("tracks") or []
                if str(track.get("uid") or "").strip()
                or str(track.get("title") or "").strip()
                or str(track.get("path") or "").strip()
            ]
            tags = [tag for tag in data.get("tags") or [] if str(tag.get("uid") or "").strip()]
        play_mode = PlayMode.PRESENCE.value
        if settings is not None:
            remembered = settings.play_mode()
            if remembered is not None:
                play_mode = remembered.value
        presence_sel = " selected" if play_mode == PlayMode.PRESENCE.value else ""
        tap_sel = " selected" if play_mode == PlayMode.TAP.value else ""
        path_options = "".join(
            f'<option value="{escape(path, quote=True)}">{escape(path)}</option>' for path in _library_paths(storage)
        )
        path_hint = '<p class="hint">Upload a track first</p>' if not path_options else ""
        uid_options = "".join(
            f'<option value="{escape(str(tag.get("uid") or ""), quote=True)}">'
            f"{escape(str(tag.get('name') or tag.get('uid') or ''))}</option>"
            for tag in tags
        )
        uid_hint = '<p class="hint">Register a figure first</p>' if not uid_options else ""
        if tracks:
            place_th = "<th>Place</th>" if pad is not None else ""
            body = "".join(_catalog_row(track, pad=pad) for track in tracks)
            library = (
                "<table>"
                "<caption>Library</caption>"
                f"<thead><tr><th>UID</th><th>Title</th><th>Path</th>{place_th}</tr></thead>"
                f"<tbody>{body}</tbody>"
                "</table>"
            )
        else:
            library = '<p class="empty">No stories yet. Upload a track, then assign a figure.</p>'
        tags_html = ""
        if tags:
            rows = "".join(
                "<tr>"
                f"<td>{escape(str(tag.get('uid') or ''))}</td>"
                "<td>"
                f'<form action="/tags/{escape(str(tag.get("uid") or ""), quote=True)}/name" method="post">'
                f'<label for="tag-name-{escape(str(tag.get("uid") or ""), quote=True)}">Name</label>'
                f'<input id="tag-name-{escape(str(tag.get("uid") or ""), quote=True)}" name="name" type="text" '
                f'value="{escape(str(tag.get("name") or ""), quote=True)}">'
                "<button>Save name</button>"
                "</form>"
                "</td>"
                "</tr>"
                for tag in tags
            )
            tags_html = (
                "<section>"
                "<h2>Figures</h2>"
                "<table>"
                "<caption>Figures</caption>"
                "<thead><tr><th>UID</th><th>Name</th></tr></thead>"
                f"<tbody>{rows}</tbody>"
                "</table>"
                "</section>"
            )
        register_section = ""
        refresh_meta = ""
        present_section = ""
        if pad is not None:
            present_section = """
<section>
<h2>Present a figure</h2>
<form action="/present" method="post">
<label for="present-uid">UID</label>
<input id="present-uid" name="uid" type="text" autocomplete="off" spellcheck="false" required>
<button>Present</button>
</form>
</section>
"""
        if register is not None:
            off_sel = "" if register.assign_mode else " selected"
            on_sel = " selected" if register.assign_mode else ""
            if register.assign_mode:
                refresh_meta = '<meta http-equiv="refresh" content="2">'
            register_section = f"""
<section>
<h2>Register figures</h2>
<form action="/register-mode" method="post">
<label for="register">NFC register</label>
<select id="register" name="register">
<option value="off"{off_sel}>Off</option>
<option value="on"{on_sel}>On — place a figure on the box</option>
</select>
<button>Save</button>
</form>
</section>
"""
        notice_key = request.query_params.get("notice", "")
        notice_text = HOME_NOTICES.get(notice_key, "")
        status = f'<p class="status" role="status">{escape(notice_text)}</p>' if notice_text else ""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{refresh_meta}
<title>RoMini</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_HREF}" rel="stylesheet">
<style>{DASHBOARD_STYLE}</style>
</head>
<body>
<main>
<header class="masthead">
<img class="mark" src="/mark.svg" width="112" height="112" alt="">
<div>
<h1>Ro<span>Mini</span></h1>
<p class="tag">Storybox</p>
<p class="lede">{escape(format_free_space(storage.free_bytes))} on the box</p>
</div>
</header>
{status}
<section>
<h2>Library</h2>
{library}
</section>
{tags_html}
{register_section}
{present_section}
<section>
<h2>Upload a track</h2>
<form action="/tracks" method="post" enctype="multipart/form-data">
<label for="file">Audio file</label>
<input id="file" type="file" name="file" accept="audio/*" required>
<button>Upload</button>
</form>
</section>
<section>
<h2>Assign a figure</h2>
<form action="/assign" method="post">
<label for="uid">Figure</label>
<select id="uid" name="uid" required>
{uid_options}
</select>
{uid_hint}
<label for="title">Title</label>
<input id="title" name="title" type="text" required>
<label for="path">File in library</label>
<select id="path" name="path" required>
{path_options}
</select>
{path_hint}
<button>Assign</button>
</form>
</section>
<section>
<h2>Play mode</h2>
<form action="/play-mode" method="post">
<label for="play_mode">How figures start a story</label>
<select id="play_mode" name="play_mode">
<option value="presence"{presence_sel}>Presence — plays while the figure sits on the box</option>
<option value="tap"{tap_sel}>Tap — tap the figure, then use the buttons</option>
</select>
<p class="hint">Presence is the default. Tap is for buttons after a tap.</p>
<button>Save play mode</button>
</form>
</section>
</main>
</body>
</html>
"""

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
