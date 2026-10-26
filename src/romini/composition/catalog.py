from collections.abc import Iterable
from pathlib import Path

from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.composition.dashboard.shared import PathCatalog
from romini.composition.sim import SimBox
from romini.features.library.import_catalog import import_catalog, include_library_tracks, library_audio_paths


def poll_catalog(
    box: SimBox,
    *,
    data_dir: Path,
    previous_mtime: float | None = None,
) -> float:
    path = data_dir / "catalog.yaml"
    library_root = data_dir / "library"

    def record(text: str) -> str:
        return include_library_tracks(text, library_audio_paths(library_root))

    PathCatalog(path).exclusive(record)
    mtime = path.stat().st_mtime
    text = path.read_text()
    if previous_mtime is not None and mtime <= previous_mtime:
        return previous_mtime
    box.library = import_catalog(
        text,
        library_root=str(library_root),
        audio_exists=lambda rel: (library_root / rel).is_file(),
    )
    SqliteCatalog(data_dir / "state.sqlite").replace_tracks(box.library.tracks)
    if previous_mtime is not None:
        box.note("catalog", "Updated catalog", headline="Catalog updated")
    return mtime


def run_catalog_ticks(box: SimBox, *, data_dir: Path, ticks: Iterable[object]) -> None:
    previous_mtime: float | None = None
    for _ in ticks:
        previous_mtime = poll_catalog(box, data_dir=data_dir, previous_mtime=previous_mtime)
