from dataclasses import dataclass, field

from romini.features.library.add_track import add_track


@dataclass
class FakeStorage:
    free_bytes: int
    files: dict[str, bytes] = field(default_factory=dict)

    def put(self, filename: str, audio: bytes) -> None:
        self.files[filename] = audio


@dataclass
class FakeNotices:
    messages: list[str] = field(default_factory=list)

    def tell(self, message: str) -> None:
        self.messages.append(message)


@dataclass
class FakeCatalog:
    paths: list[str] = field(default_factory=list)

    def list_track(self, filename: str) -> None:
        self.paths.append(filename)


def test_disk_full_does_not_store_the_track() -> None:
    storage = FakeStorage(free_bytes=0)
    notices = FakeNotices()

    stored = add_track(
        audio=b"id3",
        filename="frog.mp3",
        storage=storage,
        notices=notices,
    )

    assert stored is False
    assert storage.files == {}
    assert notices.messages == ["storage is full"]


def test_parent_adds_a_track_when_space_is_free() -> None:
    storage = FakeStorage(free_bytes=1024)
    notices = FakeNotices()
    catalog = FakeCatalog()

    stored = add_track(
        audio=b"id3",
        filename="frog.mp3",
        storage=storage,
        notices=notices,
        catalog=catalog,
    )

    assert stored is True
    assert storage.files == {"frog.mp3": b"id3"}
    assert catalog.paths == ["frog.mp3"]
    assert notices.messages == []
