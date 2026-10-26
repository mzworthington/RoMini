import yaml

from romini.features.library.assign import CatalogFile
from romini.features.play_by_tag.place_figure import CONNECT_EARCON_PATH, Earcon, StatusLed


def register_tag(
    *,
    uid: str,
    catalog: CatalogFile,
    led: StatusLed | None = None,
    earcon: Earcon | None = None,
) -> None:
    data = yaml.safe_load(catalog.read_text()) or {}
    data["tags"] = _tags_with_uid(data.get("tags") or [], uid)
    catalog.write_text(yaml.safe_dump(data, sort_keys=False))
    _announce(led, earcon)


def _tags_with_uid(rows: list, uid: str) -> list:
    tags = [row for row in rows if row.get("uid") != uid]
    existing = next((row for row in rows if row.get("uid") == uid), None)
    tags.append(_kept_tag(existing, uid))
    return tags


def _kept_tag(existing: dict | None, uid: str) -> dict:
    if existing is None:
        return {"uid": uid, "name": ""}
    kept = dict(existing)
    kept["uid"] = uid
    kept["name"] = str(existing.get("name") or "")
    return kept


def _announce(led: StatusLed | None, earcon: Earcon | None) -> None:
    if led is not None:
        led.pulse()
    if earcon is not None:
        earcon.play_earcon(CONNECT_EARCON_PATH)


def name_tag(*, uid: str, name: str, catalog: CatalogFile) -> None:
    data = yaml.safe_load(catalog.read_text()) or {}
    tags = []
    for row in data.get("tags") or []:
        if row.get("uid") == uid:
            kept = dict(row)
            kept["uid"] = uid
            kept["name"] = name
            tags.append(kept)
        else:
            tags.append(row)
    data["tags"] = tags
    catalog.write_text(yaml.safe_dump(data, sort_keys=False))
