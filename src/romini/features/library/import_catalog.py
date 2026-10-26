from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml


@dataclass
class CatalogLibrary:
    tracks: dict[str, str]

    def track_for(self, uid: str) -> str | None:
        return self.tracks.get(uid)


def import_catalog(
    text: str,
    *,
    library_root: str,
    audio_exists: Callable[[str], bool],
) -> CatalogLibrary:
    data = yaml.safe_load(text) or {}
    tracks: dict[str, str] = {}
    root = library_root.rstrip("/")
    for row in data.get("tracks") or []:
        rel = row["path"]
        if not audio_exists(rel):
            continue
        uid = row.get("uid")
        if not uid:
            continue
        if uid in tracks:
            raise ValueError(f"duplicate uid: {uid}")
        tracks[uid] = f"{root}/{rel}"
    return CatalogLibrary(tracks)


_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}


def library_audio_paths(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in _AUDIO_SUFFIXES:
            continue
        found.append(path.relative_to(root).as_posix())
    return found


def include_library_tracks(text: str, paths: list[str]) -> str:
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        data = {}
    removed = {str(item) for item in list(data.get("removed") or []) if str(item).strip()}
    rows = [
        row for row in (data.get("tracks") or []) if isinstance(row, dict) and str(row.get("path") or "") not in removed
    ]
    available = [path for path in dict.fromkeys(paths) if path not in removed]
    present = set(available)
    changed = rows != [row for row in (data.get("tracks") or []) if isinstance(row, dict)]
    for row in rows:
        path = str(row.get("path") or "")
        if not path or path in present:
            continue
        matches = [item for item in available if item.endswith(f"/{path}")]
        if len(matches) == 1:
            row["path"] = matches[0]
            changed = True
    known = {str(row.get("path") or "") for row in rows}
    for path in available:
        if path in known:
            continue
        title = PurePosixPath(path).stem.replace("-", " ").replace("_", " ")
        rows.append({"path": path, "title": title})
        known.add(path)
        changed = True
    if not changed:
        return text
    data["tracks"] = rows
    return yaml.safe_dump(data, sort_keys=False)
