import os
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import disk_usage
from typing import Literal, Protocol

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.story_audio import ElevenLabsSpeech, Speech, http_post, load_voices
from romini.composition.story_draft import GeminiScriptDraft, gemini_http_post
from romini.features.audit.record import KEEP, AuditLog, record_event
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage, add_track
from romini.features.library.assign import CatalogFile, confirm_assign
from romini.features.library.register_tag import name_tag
from romini.features.play_by_tag.now_playing import NowPlayingPlayer, describe_now_playing
from romini.features.play_by_tag.place_figure import (
    Mixer,
    PlayMode,
    on_play_pressed,
    on_volume_down,
    on_volume_set,
    on_volume_up,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def installed_version() -> str:
    try:
        return version("romini")
    except PackageNotFoundError:
        return "0.0.0"


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
    "paused": "Paused",
    "playing": "Playing",
    "needed": "Fill in the required fields",
    "volume": "Volume saved",
    "story": "Story saved",
    "character": "Character saved",
    "character-taken": "That name is already used",
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
STORY_NOTE_KEYS = ("title", "characters", "interests", "outline", "script", "character_slugs")


def _story_slug(title: str) -> str:
    parts: list[str] = []
    for ch in title.lower():
        if ch.isalnum():
            parts.append(ch)
        elif parts and parts[-1] != "-":
            parts.append("-")
    return "".join(parts).strip("-")


def _unique_track_filename(*, slug: str, taken: set[str], keep: str = "") -> str:
    stem = slug or "story"
    suffix = ".mp3"
    if keep == f"{stem}{suffix}":
        return keep
    rest = keep[len(stem) : -len(suffix)] if keep.startswith(stem) and keep.endswith(suffix) else ""
    if rest.startswith("-") and rest[1:].isdigit():
        return keep
    name = f"{stem}{suffix}"
    n = 2
    while name in taken:
        name = f"{stem}-{n}{suffix}"
        n += 1
    return name


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
        value = data.get(key)
        if key == "character_slugs" and isinstance(value, list):
            notes[key] = ",".join(str(item) for item in value if str(item).strip())
        else:
            notes[key] = str(value or "")
    return notes


def _character_slug_list(notes: dict[str, str]) -> list[str]:
    return [part for part in notes.get("character_slugs", "").split(",") if part]


def _safe_character_slugs(values: list[object]) -> list[str]:
    slugs: list[str] = []
    for value in values:
        slug = str(value).strip()
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            continue
        slugs.append(slug)
    return slugs


def _draft_character_text(notes: dict[str, str], catalog: Path | None) -> str:
    slugs = _character_slug_list(notes)
    if not slugs:
        return notes.get("characters", "")
    by_slug = {item["slug"]: item for item in _list_saved_characters(catalog)}
    parts: list[str] = []
    for slug in slugs:
        item = by_slug.get(slug)
        if item is None:
            continue
        background = item["background"].strip()
        parts.append(f"{item['name']}: {background}" if background else item["name"])
    return "\n".join(parts)


def _write_story_notes(
    root: Path,
    *,
    title: str,
    characters: str,
    interests: str,
    outline: str,
    script: str,
    character_slugs: list[str] | None = None,
) -> Path:
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
                "character_slugs": character_slugs or [],
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


def _write_character(root: Path, *, name: str, background: str, slug: str = "") -> Path:
    target = slug or _story_slug(name)
    pack = root / target if target else root
    pack.mkdir(parents=True, exist_ok=True)
    if target:
        (root / "current").write_text(f"{target}\n")
    (pack / "character.yaml").write_text(yaml.safe_dump({"name": name, "background": background}, sort_keys=True))
    return pack


def _character_name_taken(root: Path, *, name: str, except_slug: str = "") -> bool:
    want = _story_slug(name)
    folded = name.strip().casefold()
    if not want and not folded:
        return False
    for item in _list_saved_characters(root):
        if item["slug"] == except_slug:
            continue
        if item["slug"] == want or item["name"].casefold() == folded:
            return True
    return False


def _open_character_pack(root: Path, slug: str) -> None:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return
    if not (root / slug / "character.yaml").is_file():
        return
    (root / "current").write_text(f"{slug}\n")


def _clear_current(root: Path) -> None:
    pointer = root / "current"
    if pointer.is_file():
        pointer.unlink()


def _load_open_character(root: Path | None) -> dict[str, str]:
    notes = {"name": "", "background": "", "slug": ""}
    if root is None:
        return notes
    pack = _current_pack(root)
    path = pack / "character.yaml"
    if not path.is_file():
        return notes
    data = yaml.safe_load(path.read_text()) or {}
    notes["name"] = str(data.get("name") or "")
    notes["background"] = str(data.get("background") or "")
    notes["slug"] = pack.name if pack != root else ""
    return notes


def _list_saved_characters(root: Path | None) -> list[dict[str, str]]:
    if root is None or not root.is_dir():
        return []
    found: list[dict[str, str]] = []
    for path in sorted(root.iterdir()):
        yaml_path = path / "character.yaml"
        if not path.is_dir() or not yaml_path.is_file():
            continue
        data = yaml.safe_load(yaml_path.read_text()) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            continue
        found.append(
            {
                "name": name,
                "slug": path.name,
                "background": str(data.get("background") or ""),
            }
        )
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
    pack = _current_pack(root)
    if not pack.is_dir():
        return ""
    names = sorted(path.name for path in pack.iterdir() if path.is_file() and path.suffix.lower() == ".mp3")
    if not names:
        return ""
    stem = pack.name if pack != root else ""
    preferred = [name for name in names if stem and name.startswith(stem) and name.endswith(".mp3")]
    return preferred[-1] if preferred else names[0]


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


def mask_secret(value: str) -> str:
    if len(value) < 4:
        return ""
    return f"••••{value[-4:]}"


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
    characters: Path | None = None,
    secrets: Path | None = None,
    box_secrets: Path | None = None,
    drafter: ScriptDraft | None = None,
    draft_post: Callable[..., bytes] | None = None,
    speech: Speech | None = None,
    speak_post: Callable[..., bytes] | None = None,
    player: NowPlayingPlayer | None = None,
    audit: AuditLog | None = None,
) -> FastAPI:
    app = FastAPI()

    def note(action: str, summary: str) -> None:
        if audit is None:
            return
        record_event(audit, action=action, summary=summary, clock=lambda: datetime.now(UTC))

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
            tags = [
                {"uid": str(tag.get("uid") or ""), "name": str(tag.get("name") or "")}
                for tag in data.get("tags") or []
                if str(tag.get("uid") or "").strip()
            ]
            names = {tag["uid"]: tag["name"] for tag in tags}
            tracks = []
            for track in data.get("tracks") or []:
                uid = str(track.get("uid") or "")
                title = str(track.get("title") or "")
                path = str(track.get("path") or "")
                if uid.strip() or title.strip() or path.strip():
                    tracks.append(
                        {
                            "uid": uid,
                            "title": title,
                            "path": path,
                            "figure": names.get(uid) or uid,
                        }
                    )
        play_mode = PlayMode.PRESENCE.value
        if settings is not None:
            remembered = settings.play_mode()
            if remembered is not None:
                play_mode = remembered.value
        notice_key = request.query_params.get("notice", "")
        notes = _load_story_notes(stories)
        opened_character = _load_open_character(characters)
        keys = _studio_keys(secrets, box_secrets)
        audit_entries = []
        if audit is not None:
            audit_entries = [
                {
                    "when": entry.happened_at.strftime("%Y-%m-%d %H:%M"),
                    "when_iso": entry.happened_at.isoformat(),
                    "summary": entry.summary,
                }
                for entry in audit.recent(limit=KEEP)
            ]
        return templates.TemplateResponse(
            request,
            template,
            {
                "page": page,
                "page_title": page_title,
                "free_space": format_free_space(storage.free_bytes),
                "version": installed_version(),
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
                "saved_characters": _list_saved_characters(characters),
                "selected_character_slugs": _character_slug_list(notes),
                "character_name": opened_character["name"],
                "character_background": opened_character["background"],
                "opened_character_slug": opened_character["slug"],
                "elevenlabs_voices": keys["ELEVENLABS_VOICE_IDS"],
                "voices": load_voices(),
                "gemini_key_set": bool(keys["GEMINI_API_KEY"]),
                "elevenlabs_key_set": bool(keys["ELEVENLABS_API_KEY"]),
                "gemini_key_mask": mask_secret(keys["GEMINI_API_KEY"]),
                "elevenlabs_key_mask": mask_secret(keys["ELEVENLABS_API_KEY"]),
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
                "now_playing": describe_now_playing(player, tracks=tracks, tags=tags) if player is not None else None,
                "audit_entries": audit_entries,
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

    @app.get("/characters", response_class=HTMLResponse)
    def characters_page(request: Request) -> HTMLResponse:
        return render_page(request, "characters.html", page="characters", page_title="Characters")

    @app.post("/characters", response_model=None)
    async def save_character(request: Request) -> RedirectResponse:
        if characters is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name = str(form.get("name") or "")
        background = str(form.get("background") or "")
        slug = str(form.get("slug") or "").strip()
        if slug in {".", ".."} or "/" in slug or "\\" in slug:
            slug = ""
        if not name.strip():
            return _notice("/characters", "needed")
        if _character_name_taken(characters, name=name, except_slug=slug):
            return _notice("/characters", "character-taken")
        _write_character(characters, name=name, background=background, slug=slug)
        note("character", f"Saved character {name.strip() or 'untitled'}")
        return _notice("/characters", "character")

    @app.post("/characters/open", response_model=None)
    async def open_character(request: Request) -> RedirectResponse:
        if characters is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        _open_character_pack(characters, slug)
        if slug:
            note("character", f"Opened character {slug}")
        return _notice("/characters", "character")

    @app.post("/characters/new", response_model=None)
    def new_character() -> RedirectResponse:
        if characters is None:
            raise HTTPException(status_code=404)
        _clear_current(characters)
        return RedirectResponse("/characters", status_code=303)

    @app.get("/write")
    def write_page() -> RedirectResponse:
        return RedirectResponse("/stories", status_code=303)

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
            if stored:
                note("upload", f"Stored {filename}")
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
            note("assign", f"Assigned {body.title} to {body.uid}")
            return Response(status_code=204)
        form = await request.form()
        body = AssignBody(uid=str(form["uid"]), path=str(form["path"]), title=str(form["title"]))
        if not _has_required(body.uid, body.path, body.title):
            return _notice("/library", "needed")
        confirm_assign(uid=body.uid, path=body.path, title=body.title, catalog=assign_catalog)
        note("assign", f"Assigned {body.title} to {body.uid}")
        return _notice("/library", "assigned")

    class PlayModeBody(BaseModel):
        play_mode: PlayMode

    @app.put("/play-mode", status_code=204)
    def switch_play_mode(body: PlayModeBody) -> None:
        if settings is None:
            raise HTTPException(status_code=404)
        settings.remember_play_mode(body.play_mode)
        note("play-mode", f"Play mode set to {body.play_mode.value}")

    @app.post("/play-mode", response_model=None)
    async def switch_play_mode_form(request: Request) -> RedirectResponse:
        if settings is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        body = PlayModeBody.model_validate({"play_mode": str(form["play_mode"])})
        settings.remember_play_mode(body.play_mode)
        note("play-mode", f"Play mode set to {body.play_mode.value}")
        return _notice("/settings", "play-mode")

    @app.post("/play")
    def toggle_play() -> RedirectResponse:
        if player is None:
            raise HTTPException(status_code=404)
        on_play_pressed(player=player)
        if player.is_playing():
            note("play", f"Played {player.playing_path()}")
            return _notice("/", "playing")
        note("play", "Paused")
        return _notice("/", "paused")

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
        note("volume", f"Volume set to {mixer.level}")
        return _notice("/settings", "volume")

    @app.post("/play")
    def play_or_pause() -> RedirectResponse:
        if player is None:
            raise HTTPException(status_code=404)
        on_play_pressed(player=player)
        key = "paused" if not player.is_playing() else "playing"
        note("play", "Paused" if key == "paused" else "Playing")
        return _notice("/", key)

    @app.post("/place/{uid}")
    def place_figure(uid: str) -> RedirectResponse:
        if pad is None:
            raise HTTPException(status_code=404)
        pad.place(uid)
        note("place", f"Placed {uid}")
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
        note("present", f"Presented {uid}")
        return _notice("/figures", "presented")

    @app.post("/register-mode")
    async def switch_register_mode(request: Request) -> RedirectResponse:
        if register is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        register.assign_mode = str(form.get("register")) == "on"
        notice = "register-on" if register.assign_mode else "register-off"
        note("register", "Register on" if register.assign_mode else "Register off")
        return _notice("/figures", notice)

    @app.post("/tags/{uid}/name")
    async def name_registered_tag(uid: str, request: Request) -> RedirectResponse:
        if assign_catalog is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        name = str(form.get("name") or "")
        name_tag(uid=uid, name=name, catalog=assign_catalog)
        note("name", f"Named {uid} {name}".strip())
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
            character_slugs=_safe_character_slugs(list(form.getlist("character"))),
        )
        remove_extra = str(form.get("remove_extra") or "").strip()
        if remove_extra:
            _remove_story_extra(pack, remove_extra)
        else:
            await _save_story_extra(pack, form.get("extra"))
        title = str(form.get("story_title") or "").strip() or pack.name
        note("story", f"Saved story {title}")
        return _notice("/stories", "story")

    @app.post("/stories/open", response_model=None)
    async def open_story(request: Request) -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        _open_story_pack(stories, slug)
        if slug:
            note("story", f"Opened story {slug}")
        return _notice("/stories", "story")

    @app.post("/stories/new", response_model=None)
    def new_story() -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        _clear_current(stories)
        return RedirectResponse("/stories", status_code=303)

    @app.post("/stories/draft", response_model=None)
    def draft_story() -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        key = _studio_keys(secrets, box_secrets)["GEMINI_API_KEY"]
        if not key:
            return _notice("/stories", "draft-needed")
        writer = drafter or GeminiScriptDraft(api_key=key, post=draft_post or gemini_http_post)
        notes = _load_story_notes(stories)
        try:
            script = writer.draft(
                title=notes["title"],
                characters=_draft_character_text(notes, characters),
                interests=notes["interests"],
                outline=notes["outline"],
            )
        except Exception:
            return _notice("/stories", "draft-needed")
        _write_story_notes(
            stories,
            title=notes["title"],
            characters=notes["characters"],
            interests=notes["interests"],
            outline=notes["outline"],
            script=script,
            character_slugs=_character_slug_list(notes),
        )
        note("story", f"Drafted story {notes['title'] or 'untitled'}")
        return _notice("/stories", "drafted")

    @app.post("/stories/speak", response_model=None)
    async def speak_story(request: Request) -> RedirectResponse:
        if stories is None:
            raise HTTPException(status_code=404)
        keys = _studio_keys(secrets, box_secrets)
        named_voices = load_voices()
        allowed = {voice["id"] for voice in named_voices}
        form = await request.form()
        chosen = str(form.get("voice_id") or "").strip()
        voice_id = chosen if chosen in allowed else (named_voices[0]["id"] if named_voices else "")
        if not keys["ELEVENLABS_API_KEY"] or not voice_id:
            return _notice("/stories", "speak-needed")
        notes = _load_story_notes(stories)
        script = notes["script"].strip()
        if not script:
            return _notice("/stories", "speak-needed")
        speaker = speech or ElevenLabsSpeech(api_key=keys["ELEVENLABS_API_KEY"], post=speak_post or http_post)
        try:
            audio = speaker.speak(text=script, voice_id=voice_id)
        except Exception:
            return _notice("/stories", "speak-needed")
        pack = _current_pack(stories)
        slug = pack.name if pack != stories else _story_slug(notes["title"])
        filename = _unique_track_filename(
            slug=slug,
            taken=set(_library_paths(storage)),
            keep=_spoken_file_name(stories),
        )

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
            return _notice("/stories", "full")
        if pack != stories and pack.is_dir():
            for old in pack.iterdir():
                if old.is_file() and old.suffix.lower() == ".mp3" and old.name != filename:
                    old.unlink()
        pack.mkdir(parents=True, exist_ok=True)
        (pack / filename).write_bytes(audio)
        note("speak", f"Spoke story {notes['title'] or filename}")
        return _notice("/stories", "spoke")

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
        note("keys", "Saved studio keys")
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
