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
    loaded = yaml.safe_load(text) or {}
    data = loaded if isinstance(loaded, dict) else {}
    removed, rows = _kept_rows(data)
    if _apply_library(data, rows, paths, removed):
        return yaml.safe_dump(data, sort_keys=False)
    return text


def _apply_library(data: dict, rows: list, paths: list[str], removed: set[str]) -> bool:
    available = [path for path in dict.fromkeys(paths) if path not in removed]
    changed = rows != _dict_rows(data.get("tracks") or [])
    if _retarget_moved(rows, available):
        changed = True
    if _append_missing(rows, available):
        changed = True
    if not changed:
        return False
    data["tracks"] = rows
    return True


def _dict_rows(tracks: list) -> list:
    return [row for row in tracks if isinstance(row, dict)]


def _kept_rows(data: object) -> tuple[set[str], list]:
    if not isinstance(data, dict):
        return set(), []
    removed = {str(item) for item in list(data.get("removed") or []) if str(item).strip()}
    rows = [
        row for row in (data.get("tracks") or []) if isinstance(row, dict) and str(row.get("path") or "") not in removed
    ]
    return removed, rows


def _retarget_moved(rows: list, available: list[str]) -> bool:
    present = set(available)
    changed = False
    for row in rows:
        path = str(row.get("path") or "")
        if not path or path in present:
            continue
        matches = [item for item in available if item.endswith(f"/{path}")]
        if len(matches) == 1:
            row["path"] = matches[0]
            changed = True
    return changed


def _append_missing(rows: list, available: list[str]) -> bool:
    known = {str(row.get("path") or "") for row in rows}
    changed = False
    for path in available:
        if path in known:
            continue
        title = PurePosixPath(path).stem.replace("-", " ").replace("_", " ")
        rows.append({"path": path, "title": title})
        known.add(path)
        changed = True
    return changed
