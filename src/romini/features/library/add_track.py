from typing import Protocol


class Storage(Protocol):
    free_bytes: int

    def put(self, filename: str, audio: bytes) -> None: ...


class Notices(Protocol):
    def tell(self, message: str) -> None: ...


class Catalog(Protocol):
    def list_track(self, filename: str) -> None: ...


def add_track(
    *,
    audio: bytes,
    filename: str,
    storage: Storage,
    notices: Notices,
    catalog: Catalog | None = None,
) -> bool:
    if storage.free_bytes < len(audio):
        notices.tell("storage is full")
        return False
    storage.put(filename, audio)
    if catalog is not None:
        catalog.list_track(filename)
    return True
