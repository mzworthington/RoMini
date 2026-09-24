import os
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from shutil import disk_usage
from typing import Protocol
from urllib.parse import quote, unquote, urlencode

import yaml
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard.packs import (
    current_pack,
    load_story_notes,
    story_slug,
)
from romini.composition.dashboard.packs import (
    open_story_pack as open_story_pack,
)
from romini.composition.dashboard.packs import (
    write_story_notes as write_story_notes,
)
from romini.composition.story_audio import Speech, load_voices
from romini.composition.story_draft import listen_length_label, parse_duration_seconds
from romini.composition.update import describe_update_center
from romini.features.audit.record import KEEP, AuditLog
from romini.features.battery.charge import Battery
from romini.features.library.add_track import Catalog, Notices, Storage
from romini.features.library.assign import CatalogFile
from romini.features.library.track_facts import describe_audio
from romini.features.listening.log import PlayLog
from romini.features.listening.today import format_listen_length, listening_today
from romini.features.play_by_tag.now_playing import NowPlayingPlayer, describe_now_playing
from romini.features.play_by_tag.place_figure import Mixer, PlayMode
from romini.features.safety.bedtime import bedtime_due, sleep_label
from romini.features.stories.cover import cover_media_type, image_file_info, with_track_image

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["host"] = {
    "hostname": "romini",
    "address": "Not reported",
    "cpu_temp": "Not reported",
    "load": "Not reported",
    "memory": "Not reported",
    "uptime": "Not reported",
    "wifi": "Not reported",
}


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


def format_tag_uid(uid: str) -> str:
    text = unquote(uid.strip())
    compact = "".join(character for character in text if character not in ": -").upper()
    if len(compact) < 2 or len(compact) % 2 or any(character not in "0123456789ABCDEF" for character in compact):
        return text
    return ":".join(compact[index : index + 2] for index in range(0, len(compact), 2))


def figure_cover_key(uid: str) -> str | None:
    name = uid.replace("\\", "/").strip()
    if not name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        return None
    return "figures/" + name


def figure_cover_url(uid: str) -> str:
    return "/figures/cover/" + quote(uid, safe="")


def memory_fill(memory: str) -> int | None:
    used_text, _, total_text = memory.partition("/")
    try:
        used = int(used_text.strip().split()[0])
        total = int(total_text.strip().split()[0])
    except (ValueError, IndexError):
        return None
    if total <= 0:
        return None
    return min(100, round(100 * used / total))


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def _wifi_name() -> str:
    try:
        shown = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in shown.stdout.splitlines():
        active, _, ssid = line.partition(":")
        if active == "yes" and ssid.strip():
            return ssid.strip()
    return ""


def read_host_facts() -> dict[str, str]:
    hostname = socket.gethostname().strip() or "romini"
    address = ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.168.1.1", 80))
            address = sock.getsockname()[0]
    except OSError:
        address = ""
    if address.startswith("127."):
        address = ""
    temp_raw = _read_text("/sys/class/thermal/thermal_zone0/temp").strip()
    cpu_temp = ""
    if temp_raw.isdigit():
        cpu_temp = f"{int(temp_raw) / 1000:.0f}°C"
    load = ""
    try:
        one, _, _ = os.getloadavg()
        load = f"{one:.2f}"
    except OSError:
        load = ""
    memory = ""
    meminfo = _read_text("/proc/meminfo")
    total_kb = available_kb = 0
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            total_kb = int(line.split()[1])
        elif line.startswith("MemAvailable:"):
            available_kb = int(line.split()[1])
    if total_kb:
        used_mb = max(0, total_kb - available_kb) // 1024
        total_mb = total_kb // 1024
        memory = f"{used_mb} MB / {total_mb} MB"
    uptime = ""
    uptime_raw = _read_text("/proc/uptime").split()
    if uptime_raw:
        seconds = int(float(uptime_raw[0]))
        days, rest = divmod(seconds, 86400)
        hours, rest = divmod(rest, 3600)
        minutes = rest // 60
        if days:
            uptime = f"{days}d {hours}h"
        elif hours:
            uptime = f"{hours}h {minutes}m"
        else:
            uptime = f"{minutes}m"
    missing = "Not reported"
    model = _read_text("/proc/device-tree/model").replace("\x00", "").strip()
    return {
        "hostname": hostname,
        "address": address or missing,
        "cpu_temp": cpu_temp or missing,
        "load": load or missing,
        "memory": memory or missing,
        "uptime": uptime or missing,
        "wifi": _wifi_name() or missing,
        "model": model or missing,
    }


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


DRAFT_MODEL = "Gemini 3.6 Flash"
VOICE_MODEL = "ElevenLabs v3"

HOME_NOTICES = {
    "assigned": "Figure assigned",
    "play-mode": "Play mode saved",
    "uploaded": "Track stored",
    "full": "Storage is full",
    "register-on": "Place a figure on the box",
    "register-off": "Register off",
    "named": "Figure named",
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
    "muted": "Muted",
    "beep": "NFC beep saved",
    "sleep": "The box will sleep in 30 minutes",
    "sleep-off": "Bedtime cancelled",
    "power": "Power request sent",
    "image": "Cover image stored",
    "image-needed": "Choose a PNG, JPEG, GIF, or WebP image",
    "update": "Update check started",
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
    def root(self) -> Path:
        return self._root

    @property
    def free_bytes(self) -> int:
        return int(disk_usage(self._root).free)

    @property
    def total_bytes(self) -> int:
        return int(disk_usage(self._root).total)

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


def dashboard_return(raw: object, fallback: str) -> str:
    text = str(raw or "").strip()
    if not text.startswith("/") or text.startswith("//") or "\\" in text or ":" in text:
        return fallback
    return text.split("?", 1)[0]


def notice(path: str, key: str, detail: str = "") -> RedirectResponse:
    params = {"notice": key}
    if detail.strip():
        params["detail"] = detail.strip()
    return RedirectResponse(f"{path}?{urlencode(params)}", status_code=303)


def has_required(*values: str) -> bool:
    return all(value.strip() for value in values)


AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}


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


def track_cover_folder(root: Path, audio_path: str) -> Path | None:
    name = audio_path.replace("\\", "/").strip()
    if not name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        return None
    folder = (root / name).resolve()
    try:
        folder.relative_to(root.resolve())
    except ValueError:
        return None
    return folder


def save_track_cover(root: Path, audio_path: str, data: bytes) -> dict[str, object] | None:
    info = image_file_info(data)
    folder = track_cover_folder(root, audio_path)
    if info is None or folder is None:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("cover.*"):
        if old.is_file():
            old.unlink()
    filename = str(info["file"])
    (folder / filename).write_bytes(data)
    return {"file": filename, "size": info["size"], "media_type": info["media_type"]}


def locate_track_cover(root: Path | None, audio_path: str) -> tuple[Path, str] | None:
    if root is None:
        return None
    folder = track_cover_folder(root, audio_path)
    if folder is None or not folder.is_dir():
        return None
    for path in sorted(folder.glob("cover.*")):
        media = cover_media_type(path.name)
        if path.is_file() and media:
            return path, media
    return None


def track_cover_url(audio_path: str) -> str:
    return "/library/cover/" + quote(audio_path, safe="/")


def resolve_track_image(track: dict[str, object], *, covers: Path | None) -> str:
    path = str(track.get("path") or "")
    if locate_track_cover(covers, path) is None:
        return ""
    return track_cover_url(path)


def remember_track_cover(covers: Path | None, catalog: CatalogFile | None, audio_path: str) -> None:
    if covers is None or catalog is None or not audio_path.strip():
        return
    located = locate_track_cover(covers, audio_path)
    if located is None:
        return
    path, media = located
    info = {"file": path.name, "size": path.stat().st_size, "media_type": media}
    original = catalog.read_text()
    updated = with_track_image(original, paths={audio_path}, info=info)
    if updated != original:
        catalog.write_text(updated)


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
    covers: Path | None,
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
    power: object | None = None,
    updates: object | None = None,
    listening: PlayLog | None = None,
) -> HTMLResponse:
    tracks: list[dict[str, str]] = []
    tags: list[dict[str, str]] = []
    if assign_catalog is not None:
        data = yaml.safe_load(assign_catalog.read_text()) or {}
        tags = []
        for tag in data.get("tags") or []:
            uid = str(tag.get("uid") or "")
            if not uid.strip():
                continue
            key = figure_cover_key(uid)
            tags.append(
                {
                    "uid": uid,
                    "name": str(tag.get("name") or ""),
                    "uid_label": format_tag_uid(uid),
                    "image": figure_cover_url(uid) if key and locate_track_cover(covers, key) else "",
                }
            )
        names = {tag["uid"]: tag["name"] for tag in tags}
        tracks = []
        for track in data.get("tracks") or []:
            uid = str(track.get("uid") or "")
            title = str(track.get("title") or "")
            path = str(track.get("path") or "")
            artist = track.get("artist")
            artist_name = "" if artist is None else str(artist).strip()
            if uid.strip() or title.strip() or path.strip():
                read = getattr(storage, "get", None)
                audio = read(path) if callable(read) else None
                facts = describe_audio(audio) if audio else None
                tracks.append(
                    {
                        "uid": uid,
                        "title": title,
                        "artist": artist_name,
                        "path": path,
                        "suffix": Path(path).suffix.lower().lstrip(".").upper(),
                        "figure": names.get(uid) or uid,
                        "length": facts.length if facts else "",
                        "size": facts.size if facts else "",
                        "duration_sec": str(facts.duration_sec) if facts else "",
                        "image": resolve_track_image(track, covers=covers),
                    }
                )
    play_mode = PlayMode.PRESENCE.value
    sleep_at = None
    if settings is not None:
        remembered = settings.play_mode()
        if remembered is not None:
            play_mode = remembered.value
        sleep_at = settings.sleep_at()
    notice_key = request.query_params.get("notice", "")
    detail = request.query_params.get("detail", "").strip()
    bound_uids = {track["uid"] for track in tracks if track["uid"].strip()}
    unbound_tags = [tag for tag in tags if tag["uid"] not in bound_uids]
    active_figures = len(tags) - len(unbound_tags)
    figure_fill = round(100 * active_figures / len(tags)) if tags else 0
    total_bytes = getattr(storage, "total_bytes", None)
    library_root = getattr(storage, "root", None)
    disk_total = ""
    disk_used = ""
    disk_fill = 0
    if isinstance(total_bytes, int) and total_bytes > 0:
        disk_total = format_free_space(total_bytes).removesuffix(" free")
        used_bytes = max(total_bytes - storage.free_bytes, 0)
        disk_used = format_free_space(used_bytes).removesuffix(" free")
        disk_fill = min(100, round(100 * used_bytes / total_bytes))
    notes = load_story_notes(stories)
    opened_story_slug = current_pack(stories).name if stories is not None and current_pack(stories) != stories else ""
    opened_character = load_open_character(characters)
    keys = studio_keys(secrets, box_secrets)
    audit_entries = []
    if audit is not None:
        audit_entries = [
            {
                "when": entry.happened_at.strftime("%Y-%m-%d %H:%M"),
                "clock": entry.happened_at.strftime("%H:%M"),
                "when_iso": entry.happened_at.isoformat(),
                "headline": entry.headline.strip() or entry.action.replace("-", " ").capitalize(),
                "summary": entry.summary,
            }
            for entry in audit.recent(limit=KEEP)
        ]
    host = read_host_facts()
    update = describe_update_center(
        update_status,
        channel=os.environ.get("GITHUB_REPO", "mzworthington/RoMini"),
    )
    return templates.TemplateResponse(
        request,
        template,
        {
            "page": page,
            "page_title": page_title,
            "draft_model": DRAFT_MODEL,
            "voice_model": VOICE_MODEL,
            "free_space": format_free_space(storage.free_bytes),
            "version": installed_version(),
            "charge": battery.percent if battery is not None else None,
            "pack_volts": getattr(battery, "volts", None) if battery is not None else None,
            "pack_flow": getattr(battery, "flow", None) if battery is not None else None,
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
            "opened_story_slug": opened_story_slug,
            "stories_root": str(stories) if stories else "",
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
            "query": request.query_params.get("q", "").strip(),
            "unassigned": request.query_params.get("unassigned", "") == "1",
            "tracks": tracks,
            "tags": tags,
            "library_paths": library_paths(storage),
            "library_files": library_file_labels(stories, library_paths(storage)),
            "play_mode": play_mode,
            "nfc_beep": settings.nfc_beep() if settings is not None else True,
            "can_sleep": settings is not None,
            "sleep_label": sleep_label(sleep_at, datetime.now().astimezone()),
            "sleep_armed": sleep_at is not None and not bedtime_due(sleep_at, datetime.now().astimezone()),
            "presence": PlayMode.PRESENCE.value,
            "tap": PlayMode.TAP.value,
            "pad": pad is not None,
            "has_player": player is not None,
            "register": register is not None,
            "assign_mode": bool(register.assign_mode) if register is not None else False,
            "poll": (page == "figures" and register is not None and register.assign_mode)
            or update["label"] == "Checking",
            "mixer": mixer is not None,
            "volume_level": mixer.level if mixer is not None else 0,
            "volume_ceiling": mixer.ceiling if mixer is not None else 100,
            "now_playing": describe_now_playing(player, tracks=tracks, tags=tags) if player is not None else None,
            "playing_uid": (player.playing_uid() or "") if player is not None and player.is_playing() else "",
            "audit_entries": audit_entries,
            "update": update,
            "host": host,
            "memory_fill": memory_fill(host["memory"]),
            "unbound_tags": unbound_tags,
            "active_figures": active_figures,
            "figure_fill": figure_fill,
            "disk_used": disk_used,
            "disk_fill": disk_fill,
            "listen_today": (
                format_listen_length(listening_today(listening.intervals(), now=datetime.now().astimezone()))
                if listening is not None
                else "0m"
            ),
            "focus_uid": request.query_params.get("uid", "").strip(),
            "bind_prompt": request.query_params.get("bind", "") == "1",
            "disk_total": disk_total,
            "library_root": str(library_root) if library_root else "",
            "can_power": power is not None,
            "can_update": updates is not None,
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
    covers: Path | None
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
    note: Callable[..., None]
    note_failed: Callable[[str, str, BaseException], None]
    power: object | None = None
    updates: object | None = None
    listening: PlayLog | None = None
    mark_listening: Callable[[bool], None] = lambda _was_playing: None

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
            covers=self.covers,
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
            power=self.power,
            updates=self.updates,
            listening=self.listening,
        )
