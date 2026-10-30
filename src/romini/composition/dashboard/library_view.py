from pathlib import Path

from romini.composition.dashboard.media import library_paths, public_https_url, stored_size
from romini.composition.dashboard.packs import library_file_labels
from romini.features.library.import_catalog import collapse_duplicate_tracks
from romini.features.library.track_facts import format_size


def library_context(
    page: str,
    storage: object,
    stories: Path | None,
    tracks: list[dict[str, str]],
    removed: set[str],
) -> dict[str, object]:
    on_disk = _on_disk(page, storage, removed)
    titles = {track["path"]: track["title"] for track in tracks if track["path"].strip() and track["title"].strip()}
    files = library_file_labels(stories, on_disk, titles) if on_disk else []
    _attach_media(storage, files)
    return {
        "library_paths": on_disk,
        "library_files": files,
        "tracks": collapse_duplicate_tracks([*tracks, *_loose_tracks(page, tracks, files, removed, storage)]),
    }


def _on_disk(page: str, storage: object, removed: set[str]) -> list[str]:
    if page not in {"stories", "characters", "library"}:
        return []
    return [path for path in library_paths(storage) if path not in removed]


def _attach_media(storage: object, files: list[dict[str, str]]) -> None:
    for item in files:
        item["media"] = public_https_url(storage, item["path"]) or f"/library/file/{item['path']}"


def _loose_tracks(
    page: str,
    tracks: list[dict[str, str]],
    files: list[dict[str, str]],
    removed: set[str],
    storage: object,
) -> list[dict[str, str]]:
    if page != "library":
        return []
    known = {track["path"] for track in tracks}
    return [_loose_row(storage, item["path"]) for item in files if _is_loose(item["path"], known, removed)]


def _is_loose(path: str, known: set[str], removed: set[str]) -> bool:
    return path not in known and path not in removed


def _loose_row(storage: object, path: str) -> dict[str, str]:
    size_bytes = stored_size(storage, path)
    return {
        "uid": "",
        "title": Path(path).stem.replace("-", " ").replace("_", " "),
        "artist": "",
        "path": path,
        "suffix": Path(path).suffix.lower().lstrip(".").upper(),
        "figure": "",
        "length": "",
        "size": format_size(size_bytes) if size_bytes is not None else "",
        "duration_sec": "",
        "image": "",
        "media": public_https_url(storage, path),
    }
