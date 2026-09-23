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
    tags = [row for row in (data.get("tags") or []) if row.get("uid") != uid]
    existing = next((row for row in (data.get("tags") or []) if row.get("uid") == uid), None)
    if existing is None:
        tags.append({"uid": uid, "name": ""})
    else:
        kept = dict(existing)
        kept["uid"] = uid
        kept["name"] = str(existing.get("name") or "")
        tags.append(kept)
    data["tags"] = tags
    catalog.write_text(yaml.safe_dump(data, sort_keys=False))
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
