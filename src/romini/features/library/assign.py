from typing import Protocol

import yaml


class CatalogFile(Protocol):
    def read_text(self) -> str: ...

    def write_text(self, text: str) -> None: ...


def catalog_without_track(text: str, path: str) -> str:
    wanted = path.strip()
    data = yaml.safe_load(text) or {}
    if not wanted or not isinstance(data, dict):
        return text
    data["tracks"] = [row for row in list(data.get("tracks") or []) if _keep_track(row, wanted)]
    data["removed"] = _removed_paths(data, wanted)
    return yaml.safe_dump(data, sort_keys=False)


def _keep_track(row: object, wanted: str) -> bool:
    if not isinstance(row, dict):
        return True
    return str(row.get("path") or "") != wanted


def _removed_paths(data: dict, wanted: str) -> list:
    removed = [item for item in list(data.get("removed") or []) if str(item).strip() and str(item) != wanted]
    removed.append(wanted)
    return removed


def remove_track(*, path: str, catalog: CatalogFile) -> None:
    def change(text: str) -> str:
        return catalog_without_track(text, path)

    exclusive = getattr(catalog, "exclusive", None)
    if callable(exclusive):
        exclusive(change)
        return
    catalog.write_text(change(catalog.read_text()))


def rename_track(*, path: str, title: str, catalog: CatalogFile) -> None:
    data = yaml.safe_load(catalog.read_text()) or {}
    rows = list(data.get("tracks") or [])
    updated = False
    for row in rows:
        if isinstance(row, dict) and str(row.get("path") or "") == path:
            row["title"] = title
            updated = True
    if not updated:
        rows.append({"path": path, "title": title})
    data["tracks"] = rows
    catalog.write_text(yaml.safe_dump(data, sort_keys=False))


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
