from typing import Protocol

import yaml


class CatalogFile(Protocol):
    def read_text(self) -> str: ...

    def write_text(self, text: str) -> None: ...


def confirm_assign(*, uid: str, path: str, title: str, catalog: CatalogFile) -> None:
    data = yaml.safe_load(catalog.read_text()) or {}
    tracks = [row for row in (data.get("tracks") or []) if row.get("uid") != uid]
    tracks.append({"uid": uid, "path": path, "title": title, "artist": None})
    catalog.write_text(yaml.safe_dump({"tracks": tracks}, sort_keys=False))
