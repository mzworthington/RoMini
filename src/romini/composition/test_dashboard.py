from dataclasses import dataclass, field
from pathlib import Path

from romini.composition.dashboard import DiskStorage, create_dashboard
from romini.composition.sqlite_settings import SqliteSettings
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode


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


def test_dashboard_shows_free_space() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/storage")

    assert response.status_code == 200
    assert response.json() == {"free_bytes": 1024}


def test_dashboard_uploads_a_track() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024)
    notices = FakeNotices()
    catalog = FakeCatalog()
    app = create_dashboard(storage=storage, notices=notices, catalog=catalog)
    response = TestClient(app).post("/tracks", files={"file": ("frog.mp3", b"id3", "audio/mpeg")})

    assert response.status_code == 201
    assert storage.files == {"frog.mp3": b"id3"}
    assert catalog.paths == ["frog.mp3"]


def test_dashboard_assign_writes_catalog_yaml(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(),
    )
    response = TestClient(app).post(
        "/assign",
        json={
            "uid": "04aabbccddeeff",
            "path": "stories/frog-prince.mp3",
            "title": "The Frog Prince",
        },
    )

    assert response.status_code == 204
    library = import_catalog(
        catalog_path.read_text(),
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )
    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_dashboard_switches_play_mode(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    app = create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)
    response = TestClient(app).put("/play-mode", json={"play_mode": "tap"})

    assert response.status_code == 204
    assert settings.play_mode() is PlayMode.TAP


def test_disk_storage_puts_audio_and_reports_free_space(tmp_path: Path) -> None:
    storage = DiskStorage(tmp_path / "library")
    storage.put("frog.mp3", b"id3")

    assert (tmp_path / "library" / "frog.mp3").read_bytes() == b"id3"
    assert storage.free_bytes > 0


def test_dashboard_home_shows_free_space() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "1024" in response.text


def test_dashboard_home_has_upload_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert 'action="/tracks"' in response.text
    assert 'type="file"' in response.text


def test_dashboard_home_has_assign_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert 'action="/assign"' in response.text
    assert 'name="uid"' in response.text
    assert 'name="path"' in response.text
    assert 'name="title"' in response.text


def test_dashboard_assign_form_writes_catalog_yaml(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(),
    )
    response = TestClient(app).post(
        "/assign",
        data={
            "uid": "04aabbccddeeff",
            "path": "stories/frog-prince.mp3",
            "title": "The Frog Prince",
        },
    )

    assert response.status_code == 204
    library = import_catalog(
        catalog_path.read_text(),
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )
    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_dashboard_home_has_play_mode_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert 'action="/play-mode"' in response.text
    assert 'name="play_mode"' in response.text


def test_dashboard_play_mode_form_persists(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    app = create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)
    response = TestClient(app).post("/play-mode", data={"play_mode": "tap"})

    assert response.status_code == 204
    assert settings.play_mode() is PlayMode.TAP


def test_dashboard_home_lists_catalog_titles(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
    )
    response = TestClient(app).get("/")

    assert "The Frog Prince" in response.text
    assert "04aabbccddeeff" in response.text
