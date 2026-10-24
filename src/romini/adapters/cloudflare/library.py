from urllib.parse import quote

_AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}
_COVER_NAMES = ("cover.png", "cover.jpg", "cover.jpeg", "cover.webp")


class ObjectLibrary:
    def __init__(self, objects: dict[str, tuple[int, str]], *, free_bytes: int) -> None:
        self._objects = objects
        self.free_bytes = free_bytes
        self.total_bytes = free_bytes

    def paths(self) -> list[str]:
        return sorted(key for key in self._objects if _is_audio(key))

    def public_url(self, filename: str) -> str | None:
        found = self._objects.get(filename)
        if found is None or not _is_audio(filename):
            return None
        return found[1]

    def cover_url(self, filename: str) -> str | None:
        for name in _COVER_NAMES:
            key = f"covers/{filename}/{name}"
            found = self._objects.get(key)
            if found is not None:
                return found[1]
        return None

    def size(self, filename: str) -> int | None:
        found = self._objects.get(filename)
        if found is None:
            return None
        return found[0]

    def get(self, filename: str) -> bytes | None:
        return None

    def put(self, filename: str, audio: bytes) -> None:
        raise PermissionError("demo library is read only")

    def delete(self, filename: str) -> None:
        raise PermissionError("demo library is read only")


def library_from_objects(items: list[dict[str, object]], *, base_url: str) -> ObjectLibrary:
    root = base_url.rstrip("/")
    objects: dict[str, tuple[int, str]] = {}
    for item in items:
        key = str(item["key"])
        size = int(item["size"])  # type: ignore[arg-type]
        objects[key] = (size, f"{root}/{quote(key, safe='/')}")
    return ObjectLibrary(objects, free_bytes=10_000_000_000)


def _is_audio(key: str) -> bool:
    dot = key.rfind(".")
    if dot < 0:
        return False
    return key[dot:].lower() in _AUDIO_SUFFIXES
