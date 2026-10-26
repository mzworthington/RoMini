from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from romini.composition.dashboard.audition import library_file_labels, list_saved_stories, spoken_file_name
from romini.composition.dashboard.character_packs import (
    character_name_taken,
    list_saved_characters,
    load_open_character,
    open_character_pack,
    write_character,
)
from romini.composition.dashboard.pack_cursor import (
    _remember_current,
    clear_current,
    current_pack,
    open_story_pack,
    story_slug,
)
from romini.composition.story_draft import parse_duration_seconds

STORY_NOTE_KEYS = ("title", "characters", "interests", "outline", "script", "character_slugs", "duration_seconds")

__all__ = [
    "character_name_taken",
    "character_slug_list",
    "clear_current",
    "current_pack",
    "draft_character_text",
    "library_file_labels",
    "list_saved_characters",
    "list_saved_stories",
    "load_open_character",
    "load_story_notes",
    "open_character_pack",
    "open_story_pack",
    "record_spoken_track",
    "safe_character_slugs",
    "spoken_file_name",
    "story_slug",
    "unique_track_filename",
    "write_character",
    "write_story_notes",
]


@dataclass
class StoryNotes:
    title: str
    characters: str
    interests: str
    outline: str
    script: str
    character_slugs: list[str] | None = None
    duration_seconds: int | None = None


def load_story_notes(root: Path | None) -> dict[str, str]:
    notes = {key: "" for key in STORY_NOTE_KEYS}
    if root is None:
        return notes
    path = current_pack(root) / "story.yaml"
    if not path.is_file():
        return notes
    data = yaml.safe_load(path.read_text()) or {}
    for key in STORY_NOTE_KEYS:
        notes[key] = _note_value(data, key)
    return notes


def write_story_notes(root: Path, notes: StoryNotes | None = None, **fields: Any) -> Path:
    if notes is not None and fields:
        raise TypeError("pass StoryNotes or keywords")
    bound = notes if notes is not None else StoryNotes(**fields)
    return _write_notes(root, bound)


def unique_track_filename(*, slug: str, taken: set[str], keep: str = "") -> str:
    stem = slug or "story"
    suffix = ".mp3"
    if _keep_filename(stem, suffix, keep):
        return keep
    return _fresh_filename(stem, suffix, taken)


def character_slug_list(notes: dict[str, str]) -> list[str]:
    return [part for part in notes.get("character_slugs", "").split(",") if part]


def safe_character_slugs(values: list[object]) -> list[str]:
    slugs: list[str] = []
    for value in values:
        slug = str(value).strip()
        if _accepted_slug(slug):
            slugs.append(slug)
    return slugs


def draft_character_text(notes: dict[str, str], catalog: Path | None) -> str:
    slugs = character_slug_list(notes)
    if not slugs:
        return notes.get("characters", "")
    by_slug = {item["slug"]: item for item in list_saved_characters(catalog)}
    return "\n".join(_character_line(by_slug.get(slug)) for slug in slugs if by_slug.get(slug) is not None)


def record_spoken_track(pack: Path, *, filename: str, library_path: str) -> None:
    yaml_path = pack / "story.yaml"
    data = yaml.safe_load(yaml_path.read_text()) if yaml_path.is_file() else {}
    data = data or {}
    data["spoken_file"] = filename
    data["library_path"] = library_path
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_path.write_text(yaml.safe_dump(data, sort_keys=True))


def _note_value(data: object, key: str) -> str:
    value = data.get(key) if isinstance(data, dict) else None
    if key == "character_slugs" and isinstance(value, list):
        return ",".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _write_notes(root: Path, notes: StoryNotes) -> Path:
    slug = story_slug(notes.title)
    pack = root / slug if slug else root
    pack.mkdir(parents=True, exist_ok=True)
    if slug:
        _remember_current(root, slug)
    existing = _existing_story(pack / "story.yaml")
    payload = _story_payload(notes, existing)
    (pack / "story.yaml").write_text(yaml.safe_dump(payload, sort_keys=True))
    return pack


def _existing_story(yaml_path: Path) -> dict:
    if not yaml_path.is_file():
        return {}
    return yaml.safe_load(yaml_path.read_text()) or {}


def _story_payload(notes: StoryNotes, existing: dict) -> dict:
    payload = {
        "title": notes.title,
        "characters": notes.characters,
        "character_slugs": notes.character_slugs or [],
        "interests": notes.interests,
        "outline": notes.outline,
        "script": notes.script,
        "duration_seconds": parse_duration_seconds(
            notes.duration_seconds if notes.duration_seconds is not None else existing.get("duration_seconds")
        ),
    }
    for key in ("spoken_file", "library_path", "image"):
        value = existing.get(key)
        if value:
            payload[key] = value
    return payload


def _keep_filename(stem: str, suffix: str, keep: str) -> bool:
    if keep == f"{stem}{suffix}":
        return True
    rest = keep[len(stem) : -len(suffix)] if keep.startswith(stem) and keep.endswith(suffix) else ""
    return rest.startswith("-") and rest[1:].isdigit()


def _fresh_filename(stem: str, suffix: str, taken: set[str]) -> str:
    name = f"{stem}{suffix}"
    n = 2
    while name in taken:
        name = f"{stem}-{n}{suffix}"
        n += 1
    return name


def _accepted_slug(slug: str) -> bool:
    if not slug or slug in {".", ".."}:
        return False
    return "/" not in slug and "\\" not in slug


def _character_line(item: dict[str, str] | None) -> str:
    if item is None:
        return ""
    background = item["background"].strip()
    if background:
        return f"{item['name']}: {background}"
    return item["name"]

