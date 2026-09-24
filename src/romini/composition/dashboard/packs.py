from pathlib import Path

import yaml

from romini.composition.story_draft import parse_duration_seconds

STORY_NOTE_KEYS = ("title", "characters", "interests", "outline", "script", "character_slugs", "duration_seconds")


def story_slug(title: str) -> str:
    parts: list[str] = []
    for ch in title.lower():
        if ch.isalnum():
            parts.append(ch)
        elif parts and parts[-1] != "-":
            parts.append("-")
    return "".join(parts).strip("-")


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
    for key in ("spoken_file", "library_path", "image"):
        value = existing.get(key)
        if value:
            payload[key] = value
    yaml_path.write_text(yaml.safe_dump(payload, sort_keys=True))
    return pack
