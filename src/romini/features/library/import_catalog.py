from collections.abc import Callable
from dataclasses import dataclass

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
        uid = row["uid"]
        if uid in tracks:
            raise ValueError(f"duplicate uid: {uid}")
        tracks[uid] = f"{root}/{rel}"
    return CatalogLibrary(tracks)
