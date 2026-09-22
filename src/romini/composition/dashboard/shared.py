import os
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import disk_usage
from typing import Protocol
from urllib.parse import urlencode

import yaml
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.story_audio import Speech, load_voices
from romini.composition.story_draft import listen_length_label, parse_duration_seconds
from romini.composition.update import plain_update_status
from romini.features.audit.record import KEEP, AuditLog
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage
from romini.features.library.assign import CatalogFile
from romini.features.play_by_tag.now_playing import NowPlayingPlayer, describe_now_playing
from romini.features.play_by_tag.place_figure import Mixer, PlayMode

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
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
    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
        duration_seconds: int = 10,
    ) -> str: ...


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
    "stopped": "Stopped",
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
    "speak-key-id": "ElevenLabs needs the secret that starts with sk_, not the key ID",
}


def library_paths(storage: object) -> list[str]:
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

    def get(self, filename: str) -> bytes | None:
        target = (self._root / filename).resolve()
        try:
            target.relative_to(self._root.resolve())
        except ValueError:
            return None
        if not target.is_file():
            return None
        return target.read_bytes()


def notice(path: str, key: str, detail: str = "") -> RedirectResponse:
    params = {"notice": key}
    if detail.strip():
        params["detail"] = detail.strip()
    return RedirectResponse(f"{path}?{urlencode(params)}", status_code=303)


def has_required(*values: str) -> bool:
    return all(value.strip() for value in values)


AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}
STORY_NOTE_KEYS = ("title", "characters", "interests", "outline", "script", "character_slugs", "duration_seconds")


def story_slug(title: str) -> str:
    parts: list[str] = []
    for ch in title.lower():
        if ch.isalnum():
            parts.append(ch)
        elif parts and parts[-1] != "-":
            parts.append("-")
    return "".join(parts).strip("-")


def unique_track_filename(*, slug: str, taken: set[str], keep: str = "") -> str:
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


def open_story_pack(root: Path, slug: str) -> None:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return
    if not (root / slug / "story.yaml").is_file():
        return
    (root / "current").write_text(f"{slug}\n")


def current_pack(root: Path) -> Path:
    pointer = root / "current"
    if pointer.is_file():
        slug = pointer.read_text().strip()
        pack = root / slug
        if slug and pack.is_dir():
            return pack
    return root


def load_story_notes(root: Path | None) -> dict[str, str]:
    notes = {key: "" for key in STORY_NOTE_KEYS}
    if root is None:
        return notes
    path = current_pack(root) / "story.yaml"
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


def character_slug_list(notes: dict[str, str]) -> list[str]:
    return [part for part in notes.get("character_slugs", "").split(",") if part]


def safe_character_slugs(values: list[object]) -> list[str]:
    slugs: list[str] = []
    for value in values:
        slug = str(value).strip()
        if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
            continue
        slugs.append(slug)
    return slugs


def draft_character_text(notes: dict[str, str], catalog: Path | None) -> str:
    slugs = character_slug_list(notes)
    if not slugs:
        return notes.get("characters", "")
    by_slug = {item["slug"]: item for item in list_saved_characters(catalog)}
    parts: list[str] = []
    for slug in slugs:
        item = by_slug.get(slug)
        if item is None:
            continue
        background = item["background"].strip()
        parts.append(f"{item['name']}: {background}" if background else item["name"])
    return "\n".join(parts)


def write_story_notes(
    root: Path,
    *,
    title: str,
    characters: str,
    interests: str,
    outline: str,
    script: str,
    character_slugs: list[str] | None = None,
    duration_seconds: int | None = None,
) -> Path:
    slug = story_slug(title)
    pack = root / slug if slug else root
    pack.mkdir(parents=True, exist_ok=True)
    if slug:
        (root / "current").write_text(f"{slug}\n")
    existing = {}
    yaml_path = pack / "story.yaml"
    if yaml_path.is_file():
        existing = yaml.safe_load(yaml_path.read_text()) or {}
    payload = {
        "title": title,
        "characters": characters,
        "character_slugs": character_slugs or [],
        "interests": interests,
        "outline": outline,
        "script": script,
        "duration_seconds": parse_duration_seconds(
            duration_seconds if duration_seconds is not None else existing.get("duration_seconds")
        ),
    }
    for key in ("spoken_file", "library_path"):
        value = existing.get(key)
        if value:
            payload[key] = value
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=True))
    return pack


def record_spoken_track(pack: Path, *, filename: str, library_path: str) -> None:
    yaml_path = pack / "story.yaml"
    data = yaml.safe_load(yaml_path.read_text()) if yaml_path.is_file() else {}
    data = data or {}
    data["spoken_file"] = filename
    data["library_path"] = library_path
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=True))


def library_file_labels(root: Path | None, paths: list[str]) -> list[dict[str, str]]:
    titles: dict[str, str] = {}
    for story in list_saved_stories(root):
        yaml_path = (root or Path()) / story["slug"] / "story.yaml"
        data = yaml.safe_load(yaml_path.read_text()) if yaml_path.is_file() else {}
        data = data or {}
        for key in ("library_path", "spoken_file"):
            path = str(data.get(key) or "").strip()
            if path:
                titles[path] = story["title"]
    return [{"path": path, "label": f"{path} · {titles[path]}" if path in titles else path} for path in paths]


def list_saved_stories(root: Path | None) -> list[dict[str, str]]:
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


def write_character(root: Path, *, name: str, background: str, slug: str = "") -> Path:
    target = slug or story_slug(name)
    pack = root / target if target else root
    pack.mkdir(parents=True, exist_ok=True)
    if target:
        (root / "current").write_text(f"{target}\n")
    (pack / "character.yaml").write_text(yaml.safe_dump({"name": name, "background": background}, sort_keys=True))
    return pack


def character_name_taken(root: Path, *, name: str, except_slug: str = "") -> bool:
    want = story_slug(name)
    folded = name.strip().casefold()
    if not want and not folded:
        return False
    for item in list_saved_characters(root):
        if item["slug"] == except_slug:
            continue
        if item["slug"] == want or item["name"].casefold() == folded:
            return True
    return False


def open_character_pack(root: Path, slug: str) -> None:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return
    if not (root / slug / "character.yaml").is_file():
        return
    (root / "current").write_text(f"{slug}\n")


def clear_current(root: Path) -> None:
    pointer = root / "current"
    if pointer.is_file():
        pointer.unlink()


def load_open_character(root: Path | None) -> dict[str, str]:
    notes = {"name": "", "background": "", "slug": ""}
    if root is None:
        return notes
    pack = current_pack(root)
    path = pack / "character.yaml"
    if not path.is_file():
        return notes
    data = yaml.safe_load(path.read_text()) or {}
    notes["name"] = str(data.get("name") or "")
    notes["background"] = str(data.get("background") or "")
    notes["slug"] = pack.name if pack != root else ""
    return notes


def list_saved_characters(root: Path | None) -> list[dict[str, str]]:
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


def spoken_file_name(root: Path | None) -> str:
    if root is None:
        return ""
    pack = current_pack(root)
    if not pack.is_dir():
        return ""
    names = sorted(path.name for path in pack.iterdir() if path.is_file() and path.suffix.lower() == ".mp3")
    if not names:
        return ""
    stem = pack.name if pack != root else ""
    preferred = [name for name in names if stem and name.startswith(stem) and name.endswith(".mp3")]
    return preferred[-1] if preferred else names[0]


def is_audio_track(filename: str) -> bool:
    name = filename.replace("\\", "/").strip()
    return bool(name) and Path(name).suffix.lower() in AUDIO_SUFFIXES


STUDIO_KEY_NAMES = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_IDS")


def parse_env_file(path: Path) -> dict[str, str]:
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


def elevenlabs_api_key(value: str) -> str:
    key = value.strip()
    parts = key.split("-")
    if len(parts) == 5 and [len(part) for part in parts] == [8, 4, 4, 4, 12]:
        return ""
    return key


def studio_keys(secrets: Path | None, box_secrets: Path | None = None) -> dict[str, str]:
    file_vals = parse_env_file(secrets) if secrets is not None else {}
    box_vals = parse_env_file(box_secrets) if box_secrets is not None else {}

    def pick(name: str) -> str:
        return (file_vals.get(name) or box_vals.get(name) or os.environ.get(name) or "").strip()

    return {name: pick(name) for name in STUDIO_KEY_NAMES}


def mask_secret(value: str) -> str:
    if len(value) < 4:
        return ""
    return f"••••{value[-4:]}"


def write_studio_keys(
    secrets: Path,
    *,
    gemini_key: str,
    elevenlabs_key: str,
    elevenlabs_voices: str,
) -> None:
    current = parse_env_file(secrets)
    if gemini_key.strip():
        current["GEMINI_API_KEY"] = gemini_key.strip()
    usable_elevenlabs = elevenlabs_api_key(elevenlabs_key)
    if usable_elevenlabs:
        current["ELEVENLABS_API_KEY"] = usable_elevenlabs
    current["ELEVENLABS_VOICE_IDS"] = elevenlabs_voices.strip()
    secrets.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}={current[name]}\n" for name in STUDIO_KEY_NAMES if current.get(name)]
    secrets.write_text("".join(lines))
    secrets.chmod(0o600)


class PathCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path

    def read_text(self) -> str:
        return self._path.read_text()

    def write_text(self, text: str) -> None:
        self._path.write_text(text)


def render_page(
    request: Request,
    template: str,
    *,
    page: str,
    page_title: str,
    storage: Storage,
    assign_catalog: CatalogFile | None,
    settings: SqliteSettings | None,
    stories: Path | None,
    characters: Path | None,
    secrets: Path | None,
    box_secrets: Path | None,
    battery: Battery | None,
    pad: FigurePad | None,
    register: RegisterMode | None,
    mixer: Mixer | None,
    player: NowPlayingPlayer | None,
    audit: AuditLog | None,
    update_status: Path | None = None,
    flash: str = "",
) -> HTMLResponse:
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
    detail = request.query_params.get("detail", "").strip()
    notes = load_story_notes(stories)
    opened_character = load_open_character(characters)
    keys = studio_keys(secrets, box_secrets)
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
            "notice": flash or detail or HOME_NOTICES.get(notice_key, ""),
            "characters": notes["characters"],
            "outline": notes["outline"],
            "script": notes["script"],
            "story_title": notes["title"],
            "duration_seconds": parse_duration_seconds(notes.get("duration_seconds")),
            "story_length_label": listen_length_label(
                duration_seconds=parse_duration_seconds(notes.get("duration_seconds"))
            ),
            "spoken_file": spoken_file_name(stories),
            "opened_story_slug": (
                current_pack(stories).name if stories is not None and current_pack(stories) != stories else ""
            ),
            "saved_stories": list_saved_stories(stories),
            "saved_characters": list_saved_characters(characters),
            "selected_character_slugs": character_slug_list(notes),
            "character_name": opened_character["name"],
            "character_background": opened_character["background"],
            "opened_character_slug": opened_character["slug"],
            "elevenlabs_voices": keys["ELEVENLABS_VOICE_IDS"],
            "voices": load_voices(),
            "gemini_key_set": bool(keys["GEMINI_API_KEY"]),
            "elevenlabs_key_set": bool(elevenlabs_api_key(keys["ELEVENLABS_API_KEY"])),
            "elevenlabs_key_id": bool(keys["ELEVENLABS_API_KEY"])
            and not elevenlabs_api_key(keys["ELEVENLABS_API_KEY"]),
            "gemini_key_mask": mask_secret(keys["GEMINI_API_KEY"]),
            "elevenlabs_key_mask": mask_secret(elevenlabs_api_key(keys["ELEVENLABS_API_KEY"])),
            "tracks": tracks,
            "tags": tags,
            "library_paths": library_paths(storage),
            "library_files": library_file_labels(stories, library_paths(storage)),
            "play_mode": play_mode,
            "presence": PlayMode.PRESENCE.value,
            "tap": PlayMode.TAP.value,
            "pad": pad is not None,
            "has_player": player is not None,
            "register": register is not None,
            "assign_mode": bool(register.assign_mode) if register is not None else False,
            "poll": page == "figures" and register is not None and register.assign_mode,
            "mixer": mixer is not None,
            "volume_level": mixer.level if mixer is not None else 0,
            "volume_ceiling": mixer.ceiling if mixer is not None else 100,
            "now_playing": describe_now_playing(player, tracks=tracks, tags=tags) if player is not None else None,
            "playing_uid": (player.playing_uid() or "") if player is not None and player.is_playing() else "",
            "audit_entries": audit_entries,
            "update_status": plain_update_status(update_status),
        },
    )


@dataclass
class DashboardCtx:
    storage: Storage
    notices: Notices | None
    catalog: Catalog | None
    assign_catalog: CatalogFile | None
    settings: SqliteSettings | None
    pad: FigurePad | None
    register: RegisterMode | None
    mixer: Mixer | None
    battery: Battery | None
    stories: Path | None
    characters: Path | None
    secrets: Path | None
    box_secrets: Path | None
    drafter: ScriptDraft | None
    draft_post: Callable[..., bytes] | None
    speech: Speech | None
    speak_post: Callable[..., bytes] | None
    player: NowPlayingPlayer | None
    audit: AuditLog | None
    update_status: Path | None
    note: Callable[[str, str], None]
    note_failed: Callable[[str, str, BaseException], None]

    def page(self, request: Request, template: str, *, page: str, page_title: str) -> HTMLResponse:
        flash = getattr(self, "flash", "") or ""
        self.flash = ""
        return render_page(
            request,
            template,
            page=page,
            page_title=page_title,
            storage=self.storage,
            assign_catalog=self.assign_catalog,
            settings=self.settings,
            stories=self.stories,
            characters=self.characters,
            secrets=self.secrets,
            box_secrets=self.box_secrets,
            battery=self.battery,
            pad=self.pad,
            register=self.register,
            mixer=self.mixer,
            player=self.player,
            audit=self.audit,
            update_status=self.update_status,
            flash=flash,
        )
