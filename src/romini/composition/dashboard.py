import os
from collections.abc import Callable
from pathlib import Path
from shutil import disk_usage
from typing import Literal, Protocol

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.story_audio import ElevenLabsSpeech, Speech, http_post
from romini.composition.story_draft import GeminiScriptDraft, gemini_http_post
from romini.features.battery.charge import Battery
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


class ScriptDraft(Protocol):
    def draft(self, *, title: str, characters: str, interests: str, outline: str) -> str: ...


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
    "story": "Story saved",
    "keys": "Keys saved",
    "drafted": "Script drafted",
    "draft-needed": "Could not write the script",
    "spoke": "Story spoken",
    "speak-needed": "Could not speak the story",
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


def _notice(path: str, key: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?notice={key}", status_code=303)


def _has_required(*values: str) -> bool:
    return all(value.strip() for value in values)


AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}
STORY_NOTE_KEYS = ("title", "characters", "interests", "outline", "script")


def _story_slug(title: str) -> str:
    parts: list[str] = []
    for ch in title.lower():
        if ch.isalnum():
            parts.append(ch)
        elif parts and parts[-1] != "-":
            parts.append("-")
    return "".join(parts).strip("-")


def _open_story_pack(root: Path, slug: str) -> None:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return
    if not (root / slug / "story.yaml").is_file():
        return
    (root / "current").write_text(f"{slug}\n")


def _current_pack(root: Path) -> Path:
    pointer = root / "current"
    if pointer.is_file():
        slug = pointer.read_text().strip()
        pack = root / slug
        if slug and pack.is_dir():
            return pack
    return root


def _load_story_notes(root: Path | None) -> dict[str, str]:
    notes = {key: "" for key in STORY_NOTE_KEYS}
    if root is None:
        return notes
    path = _current_pack(root) / "story.yaml"
    if not path.is_file():
        return notes
    data = yaml.safe_load(path.read_text()) or {}
    for key in STORY_NOTE_KEYS:
        notes[key] = str(data.get(key) or "")
    return notes


def _write_story_notes(root: Path, *, title: str, characters: str, interests: str, outline: str, script: str) -> Path:
    slug = _story_slug(title)
    pack = root / slug if slug else root
    pack.mkdir(parents=True, exist_ok=True)
    if slug:
        (root / "current").write_text(f"{slug}\n")
    (pack / "story.yaml").write_text(
        yaml.safe_dump(
            {
                "title": title,
                "characters": characters,
                "interests": interests,
                "outline": outline,
                "script": script,
            },
            sort_keys=True,
        )
    )
    return pack


def _list_saved_stories(root: Path | None) -> list[dict[str, str]]:
    if root is None or not root.is_dir():
        return []
    found: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        yaml_path = path / "story.yaml"
        if not path.is_dir() or not yaml_path.is_file():
            continue
        data = yaml.safe_load(yaml_path.read_text()) or {}
        title = str(data.get("title") or "").strip()
        if not title:
            continue
        found.append({"title": title, "slug": path.name})
    return found


def _list_story_extras(root: Path | None) -> list[str]:
    if root is None:
        return []
    extras = _current_pack(root) / "extras"
    if not extras.is_dir():
        return []
    return sorted(path.name for path in extras.iterdir() if path.is_file() and not path.name.startswith("."))


def _spoken_file_name(root: Path | None) -> str:
    if root is None:
        return ""
    spoken = _current_pack(root) / "spoken.mp3"
    return "spoken.mp3" if spoken.is_file() else ""


async def _save_story_extra(root: Path, extra: object) -> None:
    filename = getattr(extra, "filename", None)
    if not filename or not str(filename).strip():
        return
    name = Path(str(filename).replace("\\", "/")).name
    if not name or name.startswith("."):
        return
    read = getattr(extra, "read", None)
    if not callable(read):
        return
    dest_dir = root / "extras"
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / name).write_bytes(await read())


def _remove_story_extra(root: Path, name: str) -> None:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return
    target = root / "extras" / name
    if target.is_file():
        target.unlink()


def _is_audio_track(filename: str) -> bool:
    name = filename.replace("\\", "/").strip()
    return bool(name) and Path(name).suffix.lower() in AUDIO_SUFFIXES


STUDIO_KEY_NAMES = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_IDS")


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        if not path.is_file():
            return values
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _studio_keys(secrets: Path | None, box_secrets: Path | None = None) -> dict[str, str]:
    file_vals = _parse_env_file(secrets) if secrets is not None else {}
    box_vals = _parse_env_file(box_secrets) if box_secrets is not None else {}

    def pick(name: str) -> str:
        return (file_vals.get(name) or box_vals.get(name) or os.environ.get(name) or "").strip()

    return {name: pick(name) for name in STUDIO_KEY_NAMES}


def _write_studio_keys(
    secrets: Path,
    *,
    gemini_key: str,
    elevenlabs_key: str,
    elevenlabs_voices: str,
) -> None:
    current = _parse_env_file(secrets)
    if gemini_key.strip():
        current["GEMINI_API_KEY"] = gemini_key.strip()
    if elevenlabs_key.strip():
        current["ELEVENLABS_API_KEY"] = elevenlabs_key.strip()
    current["ELEVENLABS_VOICE_IDS"] = elevenlabs_voices.strip()
    secrets.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}={current[name]}\n" for name in STUDIO_KEY_NAMES if current.get(name)]
    secrets.write_text("".join(lines))
    secrets.chmod(0o600)


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
    battery: Battery | None = None,
    stories: Path | None = None,
    secrets: Path | None = None,
    box_secrets: Path | None = None,
    drafter: ScriptDraft | None = None,
    draft_post: Callable[..., bytes] | None = None,
    speech: Speech | None = None,
    speak_post: Callable[..., bytes] | None = None,
) -> FastAPI:
    app = FastAPI()

    def brand_asset(name: str) -> FileResponse:
        path = ASSETS_DIR / name
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/svg+xml")

    def render_page(request: Request, template: str, *, page: str, page_title: str) -> HTMLResponse:
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
        notes = _load_story_notes(stories)
        keys = _studio_keys(secrets, box_secrets)
        return templates.TemplateResponse(
            request,
            template,
            {
                "page": page,
                "page_title": page_title,
                "free_space": format_free_space(storage.free_bytes),
                "charge": battery.percent if battery is not None else None,
                "notice": HOME_NOTICES.get(notice_key, ""),
                "characters": notes["characters"],
                "interests": notes["interests"],
                "outline": notes["outline"],
                "script": notes["script"],
                "story_title": notes["title"],
                "extras": _list_story_extras(stories),
                "spoken_file": _spoken_file_name(stories),
                "saved_stories": _list_saved_stories(stories),
                "elevenlabs_voices": keys["ELEVENLABS_VOICE_IDS"],
                "gemini_key_set": bool(keys["GEMINI_API_KEY"]),
                "elevenlabs_key_set": bool(keys["ELEVENLABS_API_KEY"]),
                "tracks": tracks,
                "tags": tags,
                "library_paths": _library_paths(storage),
                "play_mode": play_mode,
                "presence": PlayMode.PRESENCE.value,
                "tap": PlayMode.TAP.value,
                "pad": pad is not None,
                "register": register is not None,
                "assign_mode": bool(register.assign_mode) if register is not None else False,
                "poll": page == "figures" and register is not None and register.assign_mode,
                "mixer": mixer is not None,
                "volume_level": mixer.level if mixer is not None else 0,
                "volume_ceiling": mixer.ceiling if mixer is not None else 100,
            },
        )

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
        return render_page(request, "home.html", page="home", page_title="")

    @app.get("/figures", response_class=HTMLResponse)
    def figures_page(request: Request) -> HTMLResponse:
        return render_page(request, "figures.html", page="figures", page_title="Figures")

    @app.get("/library", response_class=HTMLResponse)
    def library_page(request: Request) -> HTMLResponse:
        return render_page(request, "library.html", page="library", page_title="Library")

    @app.get("/stories", response_class=HTMLResponse)
    def stories_page(request: Request) -> HTMLResponse:
        return render_page(request, "stories.html", page="stories", page_title="Stories")

    @app.get("/write", response_class=HTMLResponse)
    def write_page(request: Request) -> HTMLResponse:
        return render_page(request, "write.html", page="write", page_title="Write")

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request) -> HTMLResponse:
        return render_page(request, "settings.html", page="settings", page_title="Settings")

    @app.get("/storage")
    def storage_info() -> dict[str, int]:
        return {"free_bytes": storage.free_bytes}

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
            return _notice("/library", "needed")
        stored_any = False
        for item in uploads:
            filename = str(item.filename or "")
            if not _is_audio_track(filename):
                continue
            audio = await item.read()
            stored = add_track(
                audio=audio,
                filename=filename,
                storage=storage,
                notices=notices if notices is not None else Quiet(),
                catalog=catalog,
            )
            stored_any = stored_any or stored
        notice = "uploaded" if stored_any else "full"
        return _notice("/library", notice)

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
            return _notice("/library", "needed")
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)
        return _notice("/library", "assigned")

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
        return _notice("/settings", "play-mode")

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
            return _notice("/settings", "needed")
        return _notice("/settings", "volume")

    @app.post("/place/{uid}")
    def place_figure(uid: str) -> RedirectResponse:
        if pad is None:
            raise HTTPException(status_code=404)
        pad.place(uid)
        return _notice("/library", "placed")

    @app.post("/present")
    async def present_figure(request: Request) -> RedirectResponse:
        if pad is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        uid = str(form["uid"]).strip()
        if not uid:
            return _notice("/figures", "needed")
        pad.place(uid)
        return _notice("/figures", "presented")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        register.assign_mode = str(form.get("register")) == "on"
        notice = "register-on" if register.assign_mode else "register-off"
        return _notice("/figures", notice)

    @app.post("/tags/{uid}/name")
    async def name_registered_tag(uid: str, request: Request) -> RedirectResponse:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name_tag(uid=uid, name=str(form.get("name") or ""), catalog=assign_catalog)
        return _notice("/figures", "named")

    @app.post("/stories", response_model=None)
    async def save_story_notes(request: Request) -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        pack = _write_story_notes(
            stories,
            title=str(form.get("story_title") or ""),
            characters=str(form.get("characters") or ""),
            interests=str(form.get("interests") or ""),
            outline=str(form.get("outline") or ""),
            script=str(form.get("script") or ""),
        )
        remove_extra = str(form.get("remove_extra") or "").strip()
        if remove_extra:
            _remove_story_extra(pack, remove_extra)
        else:
            await _save_story_extra(pack, form.get("extra"))
        return _notice("/write", "story")

    @app.post("/stories/open", response_model=None)
    async def open_story(request: Request) -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        _open_story_pack(stories, str(form.get("slug") or "").strip())
        return _notice("/write", "story")

    @app.post("/stories/draft", response_model=None)
    def draft_story() -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        key = _studio_keys(secrets, box_secrets)["GEMINI_API_KEY"]
        if not key:
            return _notice("/write", "draft-needed")
        writer = drafter or GeminiScriptDraft(api_key=key, post=draft_post or gemini_http_post)
        notes = _load_story_notes(stories)
        try:
            script = writer.draft(
                title=notes["title"],
                characters=notes["characters"],
                interests=notes["interests"],
                outline=notes["outline"],
            )
        except Exception:
            return _notice("/write", "draft-needed")
        _write_story_notes(
            stories,
            title=notes["title"],
            characters=notes["characters"],
            interests=notes["interests"],
            outline=notes["outline"],
            script=script,
        )
        return _notice("/write", "drafted")

    @app.post("/stories/speak", response_model=None)
    def speak_story() -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        keys = _studio_keys(secrets, box_secrets)
        voices = [part.strip() for part in keys["ELEVENLABS_VOICE_IDS"].split(",") if part.strip()]
        if not keys["ELEVENLABS_API_KEY"] or not voices:
            return _notice("/write", "speak-needed")
        notes = _load_story_notes(stories)
        script = notes["script"].strip()
        if not script:
            return _notice("/write", "speak-needed")
        speaker = speech or ElevenLabsSpeech(api_key=keys["ELEVENLABS_API_KEY"], post=speak_post or http_post)
        try:
            audio = speaker.speak(text=script, voice_id=voices[0])
        except Exception:
            return _notice("/write", "speak-needed")
        pack = _current_pack(stories)
        slug = pack.name if pack != stories else _story_slug(notes["title"])
        filename = f"{slug or 'story'}.mp3"

        class Quiet:
            def tell(self, message: str) -> None:
                return

        stored = add_track(
            audio=audio,
            filename=filename,
            storage=storage,
            notices=notices if notices is not None else Quiet(),
            catalog=catalog,
        )
        if not stored:
            return _notice("/write", "full")
        (pack / "spoken.mp3").write_bytes(audio)
        return _notice("/write", "spoke")

    @app.post("/keys", response_model=None)
    async def save_keys(request: Request) -> RedirectResponse:
        if secrets is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        _write_studio_keys(
            secrets,
            gemini_key=str(form.get("gemini_key") or ""),
            elevenlabs_key=str(form.get("elevenlabs_key") or ""),
            elevenlabs_voices=str(form.get("elevenlabs_voices") or ""),
        )
        return _notice("/settings", "keys")

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
