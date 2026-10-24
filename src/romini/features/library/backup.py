import zipfile
from pathlib import Path, PurePosixPath

from romini.features.library.import_catalog import include_library_tracks

_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}


def write_backup(
    dest: object,
    *,
    catalog: Path | None,
    stories: Path | None,
    characters: Path | None,
    library: Path | None,
) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _record_library(catalog, library)
        if catalog is not None and catalog.is_file():
            archive.write(catalog, "catalog.yaml")
        _add_tree(archive, stories, "stories")
        _add_tree(archive, characters, "characters")
        _add_tree(archive, library, "library")


def _record_library(catalog: Path | None, library: Path | None) -> None:
    if catalog is None or not catalog.is_file():
        return
    recorded = include_library_tracks(catalog.read_text(), _audio_paths(library))
    if recorded != catalog.read_text():
        catalog.write_text(recorded)


def _audio_paths(root: Path | None) -> list[str]:
    if root is None or not root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in _AUDIO_SUFFIXES:
            continue
        found.append(path.relative_to(root).as_posix())
    return found


def _add_tree(archive: zipfile.ZipFile, root: Path | None, prefix: str) -> None:
    if root is None or not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        archive.write(path, f"{prefix}/{path.relative_to(root).as_posix()}")


def restore_backup(
    source: object,
    *,
    catalog: Path | None,
    stories: Path | None,
    characters: Path | None,
    library: Path | None,
) -> None:
    roots = {"stories": stories, "characters": characters, "library": library}
    with zipfile.ZipFile(source) as archive:
        planned: list[tuple[zipfile.ZipInfo, Path]] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = _member_target(info.filename, catalog=catalog, roots=roots)
            if target is not None:
                planned.append((info, target))
        for info, target in planned:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
    _record_library(catalog, library)


def _member_target(
    name: str,
    *,
    catalog: Path | None,
    roots: dict[str, Path | None],
) -> Path | None:
    if name.startswith(("/", "\\")) or "\x00" in name:
        raise ValueError("unsafe backup path")
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if not parts or ".." in parts:
        raise ValueError("unsafe backup path")
    if parts == ("catalog.yaml",):
        return catalog
    root = roots.get(parts[0])
    if parts[0] not in roots or root is None or len(parts) == 1:
        return None
    root_resolved = root.resolve()
    target = root_resolved.joinpath(*parts[1:]).resolve()
    if not target.is_relative_to(root_resolved):
        raise ValueError("unsafe backup path")
    return target
