from pathlib import Path
from urllib.parse import quote

from romini.features.library.assign import CatalogFile
from romini.features.stories.cover import cover_media_type, image_file_info, with_track_image


def figure_cover_key(uid: str) -> str | None:
    name = uid.replace("\\", "/").strip()
    if not name or name.startswith("/") or any(part in {"", ".", ".."} for part in name.split("/")):
        return None
    return "figures/" + name


def figure_cover_url(uid: str) -> str:
    return "/figures/cover/" + quote(uid, safe="")


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
