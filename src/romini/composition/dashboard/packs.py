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
