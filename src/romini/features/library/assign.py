from typing import Protocol

import yaml


class CatalogFile(Protocol):
    def read_text(self) -> str: ...

    def write_text(self, text: str) -> None: ...


def confirm_assign(*, uid: str, path: str, title: str, catalog: CatalogFile) -> None:
    data = yaml.safe_load(catalog.read_text()) or {}
    rows = list(data.get("tracks") or [])
    previous = next((row for row in rows if row.get("uid") == uid), None)
    tracks = [row for row in rows if row.get("uid") != uid]
    stored: dict[str, object] = {"uid": uid, "path": path, "title": title, "artist": None}
    if isinstance(previous, dict) and previous.get("path") == path and isinstance(previous.get("image"), dict):
        stored["image"] = previous["image"]
    tracks.append(stored)
    data["tracks"] = tracks
    catalog.write_text(yaml.safe_dump(data, sort_keys=False))
