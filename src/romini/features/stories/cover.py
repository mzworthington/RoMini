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
    image = _image_record(info)
    if not paths or image is None:
        return catalog_text
    return _stamp_rows(catalog_text, "tracks", "path", paths, image)


def with_tag_image(
    catalog_text: str,
    *,
    uid: str,
    info: dict[str, object],
) -> str:
    image = _image_record(info)
    if not uid.strip() or image is None:
        return catalog_text
    return _stamp_rows(catalog_text, "tags", "uid", {uid}, image)


def _image_record(info: dict[str, object]) -> dict[str, object] | None:
    filename = str(info.get("file") or "")
    media_type = cover_media_type(filename)
    size = info.get("size")
    if not media_type or isinstance(size, bool) or not isinstance(size, int):
        return None
    return {"file": filename, "size": size, "media_type": media_type}


def _stamp_rows(catalog_text: str, key: str, field: str, wanted: set[str], image: dict[str, object]) -> str:
    data = yaml.safe_load(catalog_text) or {}
    changed = False
    for row in data.get(key) or []:
        if str(row.get(field) or "") in wanted:
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
