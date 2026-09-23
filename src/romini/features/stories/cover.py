import yaml

COVER_LIMIT = 8 * 1024 * 1024

COVER_TYPES = {
    "cover.png": "image/png",
    "cover.jpg": "image/jpeg",
    "cover.gif": "image/gif",
    "cover.webp": "image/webp",
}

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def cover_media_type(filename: str) -> str:
    return COVER_TYPES.get(filename, "")


def image_file_info(data: bytes) -> dict[str, object] | None:
    if not data or len(data) > COVER_LIMIT:
        return None
    extension = _sniff_extension(data)
    if extension is None:
        return None
    filename = f"cover.{extension}"
    return {"file": filename, "size": len(data), "media_type": cover_media_type(filename)}


def with_track_image(
    catalog_text: str,
    *,
    paths: set[str],
    info: dict[str, object],
) -> str:
    filename = str(info.get("file") or "")
    media_type = cover_media_type(filename)
    size = info.get("size")
    if not paths or not media_type or isinstance(size, bool) or not isinstance(size, int):
        return catalog_text
    data = yaml.safe_load(catalog_text) or {}
    image = {"file": filename, "size": size, "media_type": media_type}
    changed = False
    for row in data.get("tracks") or []:
        if str(row.get("path") or "") in paths:
            row["image"] = image
            changed = True
    if not changed:
        return catalog_text
    return yaml.safe_dump(data, sort_keys=False)


def with_tag_image(
    catalog_text: str,
    *,
    uid: str,
    info: dict[str, object],
) -> str:
    filename = str(info.get("file") or "")
    media_type = cover_media_type(filename)
    size = info.get("size")
    if not uid.strip() or not media_type or isinstance(size, bool) or not isinstance(size, int):
        return catalog_text
    data = yaml.safe_load(catalog_text) or {}
    image = {"file": filename, "size": size, "media_type": media_type}
    changed = False
    for row in data.get("tags") or []:
        if str(row.get("uid") or "") == uid:
            row["image"] = image
            changed = True
    if not changed:
        return catalog_text
    return yaml.safe_dump(data, sort_keys=False)


def _sniff_extension(data: bytes) -> str | None:
    for magic, extension in _SIGNATURES:
        if data.startswith(magic):
            return extension
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "webp"
    return None
