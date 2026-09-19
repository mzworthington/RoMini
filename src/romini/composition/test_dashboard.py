from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import DiskStorage, create_dashboard
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode


@dataclass
class FakeBattery:
    percent: int | None


@dataclass
class FakeStorage:
    free_bytes: int
    files: dict[str, bytes] = field(default_factory=dict)

    def put(self, filename: str, audio: bytes) -> None:
        self.files[filename] = audio

    def paths(self) -> list[str]:
        return sorted(self.files)


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

    assert response.status_code == 200
    assert "Track stored" in response.text
    assert storage.files == {"frog.mp3": b"id3"}
    assert catalog.paths == ["frog.mp3"]


def test_dashboard_uploads_all_tracks_in_a_directory() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024)
    catalog = FakeCatalog()
    app = create_dashboard(storage=storage, catalog=catalog)
    response = TestClient(app).post(
        "/tracks",
        files=[
            ("file", ("stories/frog.mp3", b"id3", "audio/mpeg")),
            ("file", ("stories/bear.m4a", b"m4a", "audio/mp4")),
        ],
    )

    assert response.status_code == 200
    assert "Track stored" in response.text
    assert storage.files == {"stories/frog.mp3": b"id3", "stories/bear.m4a": b"m4a"}
    assert catalog.paths == ["stories/frog.mp3", "stories/bear.m4a"]


def test_dashboard_directory_upload_skips_non_audio() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024)
    catalog = FakeCatalog()
    TestClient(create_dashboard(storage=storage, catalog=catalog)).post(
        "/tracks",
        files=[
            ("file", ("stories/frog.mp3", b"id3", "audio/mpeg")),
            ("file", ("stories/.DS_Store", b"skip", "application/octet-stream")),
            ("file", ("stories/notes.txt", b"nope", "text/plain")),
        ],
    )

    assert storage.files == {"stories/frog.mp3": b"id3"}
    assert catalog.paths == ["stories/frog.mp3"]


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


def test_dashboard_assign_json_blank_title_does_not_write(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    response = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(),
        )
    ).post(
        "/assign",
        json={"uid": "04aabbccddeeff", "path": "stories/frog-prince.mp3", "title": ""},
    )

    assert response.status_code == 422
    assert catalog_path.read_text() == "tracks: []\n"


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


def test_disk_storage_lists_nested_library_files(tmp_path: Path) -> None:
    root = tmp_path / "library"
    (root / "stories").mkdir(parents=True)
    (root / "frog.mp3").write_bytes(b"id3")
    (root / "stories" / "frog-prince.mp3").write_bytes(b"id3")
    (root / ".DS_Store").write_bytes(b"skip")

    storage = DiskStorage(root)

    assert storage.paths() == ["frog.mp3", "stories/frog-prince.mp3"]


def test_dashboard_home_shows_free_space() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "1.0 KB free" in response.text


def test_dashboard_home_shows_charge_when_a_battery_is_wired() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/")
        .text
    )

    assert "72% charged" in html


def test_dashboard_home_hides_charge_without_a_battery() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "% charged" not in html


def test_dashboard_home_hides_charge_when_the_hat_is_unreadable() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=None)))
        .get("/")
        .text
    )

    assert "% charged" not in html


def test_dashboard_home_is_labelled_for_a_parent() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
    home = client.get("/").text
    library = client.get("/library").text
    settings = client.get("/settings").text

    assert "<h1" in home
    assert "<main" in home
    assert "free_bytes" not in home
    assert "bytes free" in home or "KB free" in home
    assert "<label" in library
    assert 'for="uid"' in library
    assert 'for="path"' in library
    assert 'for="title"' in library
    assert 'for="file"' in library
    assert 'for="play_mode"' in settings
    assert "<select" in settings
    assert 'value="presence"' in settings
    assert 'value="tap"' in settings


def test_dashboard_home_has_upload_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/library")

    assert 'action="/tracks"' in response.text
    assert 'type="file"' in response.text


def test_dashboard_upload_file_is_not_required_so_a_folder_can_submit() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'id="file" type="file" name="file" accept="audio/*">' in html
    assert 'id="file" type="file" name="file" accept="audio/*" required>' not in html


def test_dashboard_upload_form_has_a_folder_picker() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert '<label for="folder">Folder of tracks</label>' in html
    assert 'id="folder" type="file" name="file" accept="audio/*" webkitdirectory multiple>' in html


def test_dashboard_upload_blank_file_does_not_store() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024)
    catalog = FakeCatalog()
    response = TestClient(create_dashboard(storage=storage, catalog=catalog)).post(
        "/tracks", files={"file": ("", b"", "application/octet-stream")}
    )

    assert "Fill in the required fields" in response.text
    assert storage.files == {}
    assert catalog.paths == []


def test_dashboard_home_has_assign_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/library")

    assert 'action="/assign"' in response.text
    assert 'name="uid"' in response.text
    assert 'name="path"' in response.text
    assert 'name="title"' in response.text


def test_dashboard_assign_form_marks_required_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'id="uid" name="uid" required>' in html
    assert 'id="title" name="title" type="text" required>' in html
    assert 'id="path" name="path" required>' in html


def test_dashboard_assign_path_lists_library_files() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(
        free_bytes=1024,
        files={"frog.mp3": b"id3", "stories/frog-prince.mp3": b"id3"},
    )
    html = TestClient(create_dashboard(storage=storage)).get("/library").text

    assert '<select id="path" name="path" required>' in html
    assert '<option value="frog.mp3">' in html
    assert '<option value="stories/frog-prince.mp3">' in html


def test_dashboard_assign_path_empty_when_library_has_no_files() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert "Upload a track first" in html


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

    assert response.status_code == 200
    assert "Figure assigned" in response.text
    library = import_catalog(
        catalog_path.read_text(),
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )
    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_dashboard_assign_blank_title_does_not_write(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    response = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(),
        )
    ).post(
        "/assign",
        data={
            "uid": "04aabbccddeeff",
            "path": "stories/frog-prince.mp3",
            "title": "",
        },
    )

    assert "Fill in the required fields" in response.text
    assert catalog_path.read_text() == "tracks: []\n"


def test_dashboard_assign_blank_uid_does_not_write(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    response = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(),
        )
    ).post(
        "/assign",
        data={
            "uid": "",
            "path": "stories/frog-prince.mp3",
            "title": "The Frog Prince",
        },
    )

    assert "Fill in the required fields" in response.text
    assert catalog_path.read_text() == "tracks: []\n"


def test_dashboard_assign_blank_path_does_not_write(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")

    class PathCatalog:
        def read_text(self) -> str:
            return catalog_path.read_text()

        def write_text(self, text: str) -> None:
            catalog_path.write_text(text)

    response = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(),
        )
    ).post(
        "/assign",
        data={
            "uid": "04aabbccddeeff",
            "path": "",
            "title": "The Frog Prince",
        },
    )

    assert "Fill in the required fields" in response.text
    assert catalog_path.read_text() == "tracks: []\n"


def test_dashboard_home_has_play_mode_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/settings")

    assert 'action="/play-mode"' in response.text
    assert 'name="play_mode"' in response.text


def test_dashboard_play_mode_form_persists(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    app = create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)
    response = TestClient(app).post("/play-mode", data={"play_mode": "tap"})

    assert response.status_code == 200
    assert "Play mode saved" in response.text
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
    response = TestClient(app).get("/library")

    assert "The Frog Prince" in response.text
    assert "04aabbccddeeff" in response.text


def test_dashboard_home_lists_catalog_table(tmp_path: Path) -> None:
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
    response = TestClient(app).get("/library")

    assert "<table>" in response.text
    assert "<th>UID</th>" in response.text
    assert "<th>Title</th>" in response.text
    assert "<th>Path</th>" in response.text
    assert "stories/frog-prince.mp3" in response.text


def test_dashboard_home_lays_out_actions_in_a_flex_board_below_library() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="board"' in html
    board = html.index('class="board"')
    upload = html.index("<h2>Upload a track</h2>")
    library = html.index("<h2>Library</h2>")
    assert board < upload < library
    assert "flex-wrap: wrap" in html


def test_dashboard_catalog_table_has_caption(tmp_path: Path) -> None:
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
    response = TestClient(app).get("/library")

    assert "<caption>Library</caption>" in response.text


def test_dashboard_escapes_catalog_title(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog.mp3"\n    title: "Frog & Prince"\n'
    )
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
    )
    response = TestClient(app).get("/library")

    assert "Frog &amp; Prince" in response.text


def test_dashboard_home_has_place_form_for_each_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class FakePad:
        def place(self, uid: str) -> None:
            return

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
        pad=FakePad(),
    )
    response = TestClient(app).get("/library")

    assert 'action="/place/04aabbccddeeff"' in response.text
    assert "Place" in response.text


def test_dashboard_place_starts_the_mapped_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class FakePad:
        def __init__(self) -> None:
            self.uids: list[str] = []

        def place(self, uid: str) -> None:
            self.uids.append(uid)

    pad = FakePad()
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
        pad=pad,
    )
    response = TestClient(app).post("/place/04aabbccddeeff", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=placed"
    assert pad.uids == ["04aabbccddeeff"]


def test_dashboard_place_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).post(
        "/place/04aabbccddeeff",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=placed"


def test_dashboard_pi_profile_may_bind_lan(monkeypatch) -> None:
    from fastapi import FastAPI

    from romini.composition.dashboard import start_dashboard

    monkeypatch.setenv("ROMINI_PROFILE", "pi")
    listener = start_dashboard(FastAPI(), host="0.0.0.0", port=0)
    try:
        assert listener.port > 0
    finally:
        listener.close()


def test_dashboard_register_mode_enters_assign_mode() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = False

    register = FakeRegister()
    app = create_dashboard(storage=FakeStorage(free_bytes=1024), register=register)
    response = TestClient(app).post("/register-mode", data={"register": "on"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=register-on"
    assert register.assign_mode is True


def test_dashboard_register_mode_off_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = True

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).post(
        "/register-mode", data={"register": "off"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=register-off"


def test_dashboard_home_has_register_form() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = False

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/figures").text
    )

    assert 'action="/register-mode"' in html
    assert 'for="register"' in html
    assert 'name="register"' in html


def test_dashboard_home_lists_registered_tags(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: Frog Prince\ntracks: []\n")
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/figures")
        .text
    )

    assert "Frog Prince" in html
    assert "04aabbccddeeff" in html


def test_dashboard_assign_uid_lists_registered_tags(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: Frog Prince\ntracks: []\n")
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library")
        .text
    )

    assert '<select id="uid" name="uid" required>' in html
    assert '<option value="04aabbccddeeff">Frog Prince</option>' in html


def test_dashboard_names_a_registered_tag(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: ''\ntracks: []\n")
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
    )
    response = TestClient(app).post(
        "/tags/04aabbccddeeff/name",
        data={"name": "Frog Prince"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "Frog Prince" in catalog_path.read_text()


def test_dashboard_name_returns_with_notice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: ''\ntracks: []\n")
    response = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(catalog_path),
        )
    ).post(
        "/tags/04aabbccddeeff/name",
        data={"name": "Frog Prince"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=named"


def test_dashboard_figures_have_name_form(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: ''\ntracks: []\n")
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/figures")
        .text
    )

    assert 'action="/tags/04aabbccddeeff/name"' in html
    assert 'name="name"' in html
    assert 'for="tag-name-04aabbccddeeff"' in html


def test_dashboard_tables_right_align_last_column_and_stretch_inputs() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text

    assert "th:last-child, td:last-child { text-align: right; width: 1%; white-space: nowrap; }" in html
    assert "td:has(input) { width: 100%; }" in html


def test_dashboard_register_on_refreshes_home() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = True

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/figures").text
    )

    assert 'http-equiv="refresh"' not in html
    assert "setInterval" in html
    assert "2000" in html
    assert "location.reload" in html
    assert "activeElement" in html
    assert "defaultValue" in html
    assert 'querySelectorAll("input, textarea, select")' in html


def test_dashboard_sim_has_present_uid_form() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/figures").text

    assert 'action="/present"' in html
    assert 'id="present-uid"' in html
    assert 'for="present-uid"' in html


def test_dashboard_present_uid_is_required() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/figures").text

    assert 'id="present-uid" name="uid" type="text" autocomplete="off" spellcheck="false" required>' in html


def test_dashboard_present_blank_uid_does_not_place() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def __init__(self) -> None:
            self.uids: list[str] = []

        def place(self, uid: str) -> None:
            self.uids.append(uid)

    pad = FakePad()
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=pad)).post(
        "/present",
        data={"uid": ""},
    )

    assert "Fill in the required fields" in response.text
    assert pad.uids == []


def test_dashboard_present_places_the_uid() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def __init__(self) -> None:
            self.uids: list[str] = []

        def place(self, uid: str) -> None:
            self.uids.append(uid)

    pad = FakePad()
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=pad)).post(
        "/present",
        data={"uid": "04aabbccddeeff"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=presented"
    assert pad.uids == ["04aabbccddeeff"]


def test_dashboard_present_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).post(
        "/present",
        data={"uid": "04aabbccddeeff"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=presented"


def test_dashboard_home_shows_notice_after_action() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text

    assert 'role="status"' in html
    assert "Figure assigned" in html


def test_dashboard_assign_form_returns_to_home_with_notice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")
    app = create_dashboard(
        storage=FakeStorage(free_bytes=1024),
        assign_catalog=PathCatalog(catalog_path),
    )
    response = TestClient(app).post(
        "/assign",
        data={
            "uid": "04aabbccddeeff",
            "path": "stories/frog-prince.mp3",
            "title": "The Frog Prince",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=assigned"


def test_dashboard_play_mode_form_returns_to_home_with_notice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)).post(
        "/play-mode", data={"play_mode": "tap"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings?notice=play-mode"


def test_dashboard_upload_form_returns_to_home_with_notice() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024), catalog=FakeCatalog())
    response = TestClient(app).post(
        "/tracks",
        files={"file": ("frog.mp3", b"id3", "audio/mpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=uploaded"


def test_dashboard_home_uses_romini_brand() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "--story-coral: #FF6B6B" in html
    assert "--magic-ochre: #F7B731" in html
    assert "--olive-sun: #E5B887" in html
    assert "--warm-chestnut: #4A2E18" in html
    assert "--midnight-navy: #1E293B" in html
    assert "--cloud-foam: #F8FAFC" in html
    assert "Nunito" in html
    assert "Quicksand" in html
    assert 'src="/mark.svg"' in html
    assert 'href="/favicon.svg"' in html
    assert "Storybox" in html


def test_dashboard_serves_logo() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/logo.svg")

    assert response.status_code == 200
    assert "image/svg" in response.headers["content-type"]
    assert b"<svg" in response.content
    assert b"#E5B887" in response.content
    assert b"#4A2E18" in response.content


def test_dashboard_serves_mark() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/mark.svg")

    assert response.status_code == 200
    assert "image/svg" in response.headers["content-type"]
    assert b"#E5B887" in response.content
    assert b"STORYBOX" not in response.content


def test_dashboard_serves_favicon() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
    response = client.get("/favicon.svg")
    mark = client.get("/mark.svg").content

    assert response.status_code == 200
    assert "image/svg" in response.headers["content-type"]
    assert b"#E5B887" in response.content
    assert b"#4A2E18" in response.content
    assert b"data:image/png" in response.content
    assert b"data:image/png" in mark
    assert len(response.content) < len(mark)


def test_dashboard_home_renders_from_jinja_template() -> None:
    from fastapi.testclient import TestClient

    from romini.composition import dashboard as dashmod

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    source = Path(dashmod.__file__).read_text()
    template = Path(dashmod.__file__).parent / "templates" / "home.html"

    assert template.is_file()
    assert "{%" in template.read_text()
    assert "<!DOCTYPE html>" not in source
    assert "DASHBOARD_STYLE" not in source
    assert "REGISTER_POLL" not in source
    assert "<main" in html
    assert "1.0 KB free" in html


@dataclass
class FakeMixer:
    level: int
    ceiling: int = 100

    def set_level(self, level: int) -> None:
        self.level = level


def test_dashboard_home_hides_volume_without_a_mixer() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
    home = client.get("/").text
    html = client.get("/settings").text

    assert ">Volume<" not in home
    assert 'action="/volume"' not in home
    assert ">Volume<" not in html
    assert 'action="/volume"' not in html


def test_dashboard_settings_shows_volume_when_mixer_is_wired() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
    home = client.get("/").text
    html = client.get("/settings").text

    assert "<h2>Volume</h2>" not in home
    assert 'action="/volume"' not in home
    assert "<h2>Volume</h2>" in html
    assert "10 of 100" in html
    assert 'action="/volume"' in html
    assert 'name="step" value="down"' in html
    assert 'name="step" value="up"' in html
    assert ">Quieter<" in html
    assert ">Louder<" in html
    assert 'id="volume-level"' in html
    assert 'for="volume-level"' in html
    assert 'type="range"' in html
    assert 'max="100"' in html
    assert 'value="10"' in html
    assert "power button" in html.lower()


def test_dashboard_volume_quieter_steps_the_mixer() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "down"},
    )

    assert mixer.level == 9
    assert "Volume saved" in response.text
    assert "9 of 100" in response.text


def test_dashboard_volume_louder_steps_the_mixer() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "up"},
    )

    assert mixer.level == 11
    assert "Volume saved" in response.text
    assert "11 of 100" in response.text


def test_dashboard_volume_set_jumps_to_the_level() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10)
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"level": "42"},
    )

    assert mixer.level == 42
    assert "Volume saved" in response.text
    assert "42 of 100" in response.text


def test_dashboard_volume_set_clamps_to_the_ceiling() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=10, ceiling=100)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"level": "200"},
    )

    assert mixer.level == 100


def test_dashboard_volume_louder_at_ceiling_stays() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=100, ceiling=100)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "up"},
    )

    assert mixer.level == 100


def test_dashboard_volume_quieter_at_zero_stays() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=0)
    TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer)).post(
        "/volume",
        data={"step": "down"},
    )

    assert mixer.level == 0


def test_dashboard_volume_without_mixer_is_missing() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).post(
        "/volume",
        data={"step": "up"},
    )

    assert response.status_code == 404


def test_dashboard_volume_form_returns_to_settings_with_notice() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10))).post(
        "/volume", data={"step": "up"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings?notice=volume"


def test_dashboard_keeps_story_notes_after_save(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={"characters": "Romy", "interests": "trains", "outline": "a station"},
    )
    html = client.get("/write").text

    assert ">Romy</textarea>" in html
    assert ">trains</textarea>" in html
    assert ">a station</textarea>" in html


def test_dashboard_lists_an_extra_file_on_the_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={"characters": "", "interests": "", "outline": ""},
        files={"extra": ("scribbles.txt", b"hi", "text/plain")},
    )
    html = client.get("/write").text

    assert "scribbles.txt" in html


def test_dashboard_removes_an_extra_file_without_deleting_the_spoken_mp3(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    spoken = tmp_path / "spoken.mp3"
    spoken.write_bytes(b"id3")
    extras = tmp_path / "extras"
    extras.mkdir()
    (extras / "scribbles.txt").write_bytes(b"hi")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"remove_extra": "scribbles.txt"})
    html = client.get("/write").text

    assert "scribbles.txt" not in html
    assert spoken.read_bytes() == b"id3"


def test_dashboard_home_has_labelled_story_note_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="characters"' in html
    assert ">Characters<" in html
    assert 'for="interests"' in html
    assert "Points to cover / interests" in html
    assert 'for="outline"' in html
    assert "Story outline" in html


def test_dashboard_home_has_labelled_story_title() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="story-title"' in html
    assert "Story title" in html


def test_dashboard_draft_and_speak_controls_are_labelled() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'action="/stories/draft"' in html
    assert ">Draft script<" in html
    assert 'action="/stories/speak"' in html
    assert ">Speak script<" in html


def test_dashboard_saved_stories_empty_when_none_saved(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path)).get("/stories").text

    assert "<h2>Saved stories</h2>" in html
    assert "No saved stories yet" in html


def test_dashboard_lists_a_saved_story_after_save(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "a ride",
        },
    )
    html = client.get("/stories").text

    assert "No saved stories yet" not in html
    assert "The little station" in html
    assert "Open The little station" in html


def test_dashboard_saved_stories_use_the_home_jump_list(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    html = client.get("/stories").text

    assert 'class="jumps"' in html
    assert 'class="jump"' in html
    assert "<strong>The little station</strong>" in html


def test_dashboard_opening_another_story_shows_that_story_notes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "one",
        },
    )
    client.post(
        "/stories",
        data={
            "story_title": "The red helmet",
            "characters": "Rowmy",
            "interests": "hats",
            "outline": "two",
        },
    )
    client.post("/stories/open", data={"slug": "the-little-station"})
    html = client.get("/write").text
    listed = client.get("/stories").text

    assert ">Romy</textarea>" in html
    assert ">Rowmy</textarea>" not in html
    assert 'value="The little station"' in html
    assert "The red helmet" in listed


def test_dashboard_keeps_the_script_after_save(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "a ride",
            "script": "Once upon a time",
        },
    )
    html = client.get("/write").text

    assert 'for="script"' in html
    assert ">Once upon a time</textarea>" in html


def test_dashboard_home_when_box_secrets_are_unreadable(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    locked = tmp_path / "etc-romini"
    locked.mkdir()
    env = locked / "env"
    env.write_text("GITHUB_TOKEN=secret\nGEMINI_API_KEY=from-box\n")
    locked.chmod(0o000)
    try:
        response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), box_secrets=env)).get("/")
    finally:
        locked.chmod(0o700)

    assert response.status_code == 200
    assert "from-box" not in response.text
    assert "secret" not in response.text


def test_dashboard_keys_form_is_labelled() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "<h2>Keys</h2>" in html
    assert 'for="gemini-key"' in html
    assert "Gemini key" in html
    assert 'for="elevenlabs-key"' in html
    assert "ElevenLabs key" in html
    assert 'type="password"' in html


def test_dashboard_saved_keys_are_set_not_shown(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), secrets=secrets))
    client.post(
        "/keys",
        data={
            "gemini_key": "gem-secret",
            "elevenlabs_key": "el-secret",
        },
    )
    html = client.get("/settings").text

    assert "gem-secret" not in html
    assert "el-secret" not in html
    assert "Gemini key is set" in html
    assert "ElevenLabs key is set" in html
    text = secrets.read_text()
    assert "GEMINI_API_KEY=gem-secret" in text
    assert "ELEVENLABS_API_KEY=el-secret" in text


@dataclass
class FakeDrafter:
    script: str
    calls: list[dict[str, str]] = field(default_factory=list)

    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
    ) -> str:
        self.calls.append(
            {
                "title": title,
                "characters": characters,
                "interests": interests,
                "outline": outline,
            }
        )
        return self.script


@dataclass
class FakeSpeech:
    audio: bytes
    calls: list[dict[str, str]] = field(default_factory=list)

    def speak(self, *, text: str, voice_id: str) -> bytes:
        self.calls.append({"text": text, "voice_id": voice_id})
        return self.audio


def test_dashboard_draft_fills_script_from_notes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    drafter = FakeDrafter(script="Rowmy waited at the station. [pause]")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            drafter=drafter,
        )
    )
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "a ride",
            "script": "",
        },
    )
    client.post("/stories/draft")
    html = client.get("/write").text

    assert ">Rowmy waited at the station. [pause]</textarea>" in html
    assert drafter.calls == [
        {
            "title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "a ride",
        }
    ]
    assert "gem-secret" not in html


def test_dashboard_draft_without_gemini_key_explains_and_keeps_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    drafter = FakeDrafter(script="should not appear")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=tmp_path / "studio.env",
            drafter=drafter,
        )
    )
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "characters": "Romy",
            "interests": "trains",
            "outline": "a ride",
            "script": "Once upon a time",
        },
    )
    html = client.post("/stories/draft").text

    assert "Could not write the script" in html
    assert ">Once upon a time</textarea>" in html
    assert drafter.calls == []


def test_dashboard_draft_when_writer_fails_explains_and_keeps_script(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class BoomDrafter:
        def draft(self, *, title: str, characters: str, interests: str, outline: str) -> str:
            raise RuntimeError("offline")

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            drafter=BoomDrafter(),
        )
    )
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "script": "Once upon a time",
        },
    )
    html = client.post("/stories/draft").text

    assert "Could not write the script" in html
    assert ">Once upon a time</textarea>" in html


def test_dashboard_draft_uses_box_secrets_when_studio_file_is_empty(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    box_env = tmp_path / "romini.env"
    box_env.write_text("GEMINI_API_KEY=from-box\n")
    drafter = FakeDrafter(script="Rowmy waited at the station.")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path / "stories",
            secrets=tmp_path / "studio.env",
            box_secrets=box_env,
            drafter=drafter,
        )
    )
    client.post("/stories", data={"story_title": "The little station", "outline": "a ride"})
    html = client.post("/stories/draft").text

    assert ">Rowmy waited at the station.</textarea>" in html
    assert "from-box" not in html
    assert drafter.calls


def test_dashboard_draft_uses_gemini_when_no_drafter_is_injected(tmp_path: Path) -> None:
    import json

    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    posts: list[tuple[str, dict[str, str]]] = []

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        posts.append((url, headers))
        return json.dumps(
            {"candidates": [{"content": {"parts": [{"text": "Rowmy waited at the station. [pause]"}]}}]}
        ).encode()

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            draft_post=post,
        )
    )
    client.post("/stories", data={"story_title": "The little station", "outline": "a ride"})
    html = client.post("/stories/draft").text

    assert ">Rowmy waited at the station. [pause]</textarea>" in html
    assert posts
    assert "gem-secret" not in html


def test_dashboard_speak_stores_mp3_in_library_and_on_the_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk-secret\nELEVENLABS_VOICE_IDS=voice-a,voice-b\n")
    storage = FakeStorage(free_bytes=1024)
    catalog = FakeCatalog()
    speech = FakeSpeech(audio=b"ID3ok")
    client = TestClient(
        create_dashboard(
            storage=storage,
            catalog=catalog,
            stories=tmp_path,
            secrets=secrets,
            speech=speech,
        )
    )
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "script": "Rowmy waited at the station. [pause]",
        },
    )
    html = client.post("/stories/speak").text
    library = client.get("/library").text

    assert storage.files["the-little-station.mp3"] == b"ID3ok"
    assert catalog.paths == ["the-little-station.mp3"]
    assert (tmp_path / "the-little-station" / "spoken.mp3").read_bytes() == b"ID3ok"
    assert "spoken.mp3" in html
    assert "the-little-station.mp3" in library
    assert speech.calls == [{"text": "Rowmy waited at the station. [pause]", "voice_id": "qXdtsJJ9LgnQ8Z2TYfav"}]
    assert "sk-secret" not in html


def test_dashboard_speak_uses_the_voice_you_picked(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.story_audio import load_voices

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk-secret\n")
    speech = FakeSpeech(audio=b"ID3ok")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            speech=speech,
        )
    )
    client.post(
        "/stories",
        data={"story_title": "The little station", "script": "Rowmy waited at the station."},
    )
    chosen = load_voices()[1]
    client.post("/stories/speak", data={"voice_id": chosen["id"]})

    assert speech.calls == [{"text": "Rowmy waited at the station.", "voice_id": chosen["id"]}]


def test_dashboard_speak_without_elevenlabs_key_explains_and_keeps_spoken_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_IDS", raising=False)
    speech = FakeSpeech(audio=b"new")
    storage = FakeStorage(free_bytes=1024)
    client = TestClient(
        create_dashboard(
            storage=storage,
            stories=tmp_path,
            secrets=tmp_path / "studio.env",
            speech=speech,
        )
    )
    client.post(
        "/stories",
        data={"story_title": "The little station", "script": "Rowmy waited at the station."},
    )
    (tmp_path / "the-little-station" / "spoken.mp3").write_bytes(b"old")
    html = client.post("/stories/speak").text

    assert "Could not speak the story" in html
    assert (tmp_path / "the-little-station" / "spoken.mp3").read_bytes() == b"old"
    assert storage.files == {}
    assert speech.calls == []


def test_dashboard_opening_a_story_shows_its_spoken_file(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    first = tmp_path / "the-little-station"
    first.mkdir()
    (first / "story.yaml").write_text("title: The little station\nscript: hello\n")
    (first / "spoken.mp3").write_bytes(b"id3")
    second = tmp_path / "the-red-helmet"
    second.mkdir()
    (second / "story.yaml").write_text("title: The red helmet\nscript: later\n")
    (tmp_path / "current").write_text("the-red-helmet\n")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories/open", data={"slug": "the-little-station"})
    html = client.get("/write").text

    assert "spoken.mp3" in html
    assert "The little station" in html


def test_dashboard_speak_again_replaces_the_spoken_file(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk-secret\nELEVENLABS_VOICE_IDS=voice-a\n")
    storage = FakeStorage(free_bytes=1024)
    speech = FakeSpeech(audio=b"first")
    client = TestClient(
        create_dashboard(
            storage=storage,
            stories=tmp_path,
            secrets=secrets,
            speech=speech,
        )
    )
    client.post(
        "/stories",
        data={"story_title": "The little station", "script": "first script"},
    )
    client.post("/stories/speak")
    speech.audio = b"second"
    client.post("/stories", data={"story_title": "The little station", "script": "second script"})
    client.post("/stories/speak")

    assert storage.files["the-little-station.mp3"] == b"second"
    assert (tmp_path / "the-little-station" / "spoken.mp3").read_bytes() == b"second"
    assert speech.calls[-1] == {"text": "second script", "voice_id": "qXdtsJJ9LgnQ8Z2TYfav"}


def test_dashboard_pages_split_parent_jobs() -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class Pad:
        def place(self, uid: str) -> None:
            return

    @dataclass
    class Register:
        assign_mode: bool = False

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            mixer=FakeMixer(level=10),
            register=Register(),
            pad=Pad(),
        )
    )
    home = client.get("/").text
    figures = client.get("/figures").text
    library = client.get("/library").text
    stories = client.get("/stories").text
    write = client.get("/write").text
    settings = client.get("/settings").text

    for page in (home, figures, library, stories, write, settings):
        assert "<nav" in page
        assert 'href="/"' in page
        assert ">Home<" in page
        assert 'href="/figures"' in page
        assert ">Figures<" in page
        assert 'href="/library"' in page
        assert ">Library<" in page
        assert 'href="/stories"' in page
        assert ">Stories<" in page
        assert 'href="/write"' in page
        assert ">Write<" in page
        assert 'href="/settings"' in page
        assert ">Settings<" in page

    assert "<h2>Volume</h2>" not in home
    assert "<h2>Keys</h2>" not in home
    assert 'action="/assign"' not in home
    assert "<h2>Write a story</h2>" not in home
    assert "<h2>Saved stories</h2>" not in home
    assert 'action="/assign"' not in figures
    assert 'action="/tracks"' not in figures
    assert 'action="/register-mode"' in figures
    assert 'action="/assign"' in library
    assert 'action="/tracks"' in library
    assert "<h2>Volume</h2>" not in figures
    assert "<h2>Saved stories</h2>" in stories
    assert 'for="characters"' in write
    assert 'action="/stories/draft"' in write
    assert "<h2>Keys</h2>" in settings
    assert 'for="play_mode"' in settings
    assert "<h2>Volume</h2>" in settings


def test_dashboard_library_page_puts_upload_and_assign_above_the_catalog() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'href="/library"' in html
    assert ">Library<" in html
    assert 'aria-current="page"' in html
    board = html.index('class="board"')
    upload = html.index("<h2>Upload a track</h2>")
    assign = html.index("<h2>Assign a figure</h2>")
    library = html.index("<h2>Library</h2>")
    assert board < upload < assign < library
    assert 'action="/tracks"' in html
    assert 'action="/assign"' in html


def test_dashboard_figures_page_puts_actions_above_the_figure_list() -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class Pad:
        def place(self, uid: str) -> None:
            return

    @dataclass
    class Register:
        assign_mode: bool = False

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                register=Register(),
                pad=Pad(),
            )
        )
        .get("/figures")
        .text
    )

    board = html.index('class="board"')
    register = html.index("<h2>Register figures</h2>")
    present = html.index("<h2>Present a figure</h2>")
    figures = html.index("<h2>Figures</h2>")
    assert board < register < present < figures
    assert 'action="/tracks"' not in html
    assert 'action="/assign"' not in html
    assert "<h2>Library</h2>" not in html


def test_dashboard_chrome_sits_in_the_same_column_as_the_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    shell = html.index('class="shell"')
    header = html.index("<header")
    main = html.index("<main")
    end_main = html.index("</main>")
    end_shell = html.index("</div>", end_main)

    assert shell < header < main < end_main < end_shell
    assert "max-width: 52rem" in html
    assert ">RoMini<" in html.replace("<span>", "").replace("</span>", "")
    assert 'href="/figures"' in html
    assert "Toys" in html
    assert 'href="/library"' in html
    assert 'href="/stories"' in html
    assert 'href="/write"' in html


def test_dashboard_home_shows_the_box_picture() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'src="/logo.svg"' in html
    assert 'class="welcome"' in html


def test_dashboard_write_page_lets_you_pick_a_named_voice() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="voice"' in html
    assert ">Voice<" in html
    assert 'name="voice_id"' in html
    assert 'action="/stories/speak"' in html
