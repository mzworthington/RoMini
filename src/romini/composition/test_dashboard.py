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

    def get(self, filename: str) -> bytes | None:
        return self.files.get(filename)


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


def test_dashboard_shows_the_installed_version() -> None:
    from importlib.metadata import version

    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert f"v{version('romini')}" in html


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


def test_dashboard_tap_mode_copy_says_tap_starts_and_same_figure_pauses() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "tap the figure to start" in html
    assert "same figure again to pause" in html


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
    assert "<th>Figure</th>" in response.text
    assert "<th>Title</th>" in response.text
    assert "<th>Path</th>" in response.text
    assert "stories/frog-prince.mp3" in response.text


def test_dashboard_library_table_shows_figure_name_not_uid(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Banana"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/romy-and-the-banana.mp3"\n'
        '    title: "Romy and the banana"\n'
    )
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
    table = html[html.index("<caption>Library</caption>") : html.index("</table>")]

    assert "<th>Figure</th>" in table
    assert "<th>UID</th>" not in table
    assert "Banana" in table
    assert "04aabbccddeeff" not in table


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
        data={"outline": "trains, then a station"},
    )
    html = client.get("/write").text

    assert ">trains, then a station</textarea>" in html
    assert "<legend>Characters</legend>" in html


def test_dashboard_keeps_story_length_after_save(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"duration_seconds": "240", "outline": "a ride"})
    html = client.get("/write").text

    assert 'id="story-length"' in html
    assert 'value="240"' in html
    assert "4 minutes" in html


def test_dashboard_home_has_labelled_story_note_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="outline"' in html
    assert "Story outline" in html
    assert 'for="interests"' not in html
    assert "Points to cover / interests" not in html
    assert 'for="extra"' not in html
    assert "Extra files" not in html
    assert "<legend>Characters</legend>" in html
    assert 'for="characters"' not in html


def test_dashboard_home_has_labelled_story_title() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="story-title"' in html
    assert "Story title" in html
    assert 'id="story-title" name="story_title" type="text" required' in html


def test_stories_page_has_story_length_slider() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'for="story-length"' in html
    assert "Story length" in html
    assert 'id="story-length"' in html
    assert 'name="duration_seconds"' in html
    assert 'type="range"' in html
    assert 'min="10"' in html
    assert 'max="600"' in html


def test_stories_page_shows_story_length_in_time() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'id="story-length-now"' in html
    assert "10 seconds" in html


def test_stories_length_slider_has_live_time_label() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/write").text

    assert 'oninput="updateStoryLength(this.value)"' in html
    assert "function updateStoryLength" in html


def test_dashboard_draft_and_speak_controls_are_labelled(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text

    assert 'action="/stories/draft"' in html
    assert ">Draft script<" in html
    assert 'action="/stories/speak"' in html
    assert ">Speak script<" in html


def test_dashboard_draft_sits_under_save_in_the_write_section(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    empty = client.get("/stories").text

    assert 'action="/stories/draft"' not in empty
    assert ">Draft script<" not in empty

    client.post("/stories", data={"story_title": "The little station"})
    html = client.get("/stories").text
    write = html.split("<h2>Write a story</h2>", 1)[1].split("<h2>Saved stories</h2>", 1)[0]

    assert write.index(">Save story<") < write.index('action="/stories/draft"')
    assert write.index('action="/stories/draft"') < write.index("</section>")
    assert "#script" in html
    assert "min-height: 22rem" in html


def test_dashboard_saved_stories_empty_when_none_saved(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path)).get("/stories").text

    assert "<h2>Saved stories</h2>" in html
    assert "No saved stories yet" in html


def test_dashboard_nav_has_stories_without_a_separate_write_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text

    assert 'href="/stories"' in html
    assert ">Stories<" in html
    assert 'href="/write"' not in html
    assert ">Write<" not in html


def test_dashboard_characters_page_has_labelled_create_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/characters").text

    assert "<h2>Add a character</h2>" in html
    assert 'for="character-name"' in html
    assert ">Name<" in html
    assert 'for="character-background"' in html
    assert "Background and history" in html


def test_dashboard_nav_has_characters_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/characters").text

    assert 'href="/characters"' in html
    assert ">Characters<" in html
    assert 'aria-current="page"' in html


def test_dashboard_lists_a_saved_character_after_save(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post(
        "/characters",
        data={"name": "Romy", "background": "Loves trains and bedtime."},
    )
    html = client.get("/characters").text

    assert "No characters yet" not in html
    assert "Romy" in html
    assert "Loves trains and bedtime." in html


def test_dashboard_opening_a_character_fills_the_form(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    client.post("/characters/open", data={"slug": "romy"})
    html = client.get("/characters").text

    assert 'value="Romy"' in html
    assert ">Loves trains.</textarea>" in html
    assert ">Open<" in html


def test_dashboard_rejects_a_second_character_with_the_same_name(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    html = client.post("/characters", data={"name": "Romy", "background": "A different Romy."}).text

    assert "That name is already used" in html
    assert ">Loves trains.</textarea>" in html
    assert "A different Romy." not in html


def test_dashboard_new_character_clears_the_form(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    saved = client.get("/characters").text
    html = client.post("/characters/new").text

    assert ">New character<" in saved
    assert saved.index(">New character<") < saved.index("<h2>Edit a character</h2>")
    assert 'value="Romy"' not in html
    assert 'type="hidden" name="slug"' not in html
    assert ">Open<" in html


def test_dashboard_saving_an_opened_character_updates_background(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    client.post(
        "/characters",
        data={"name": "Romy", "background": "Now loves boats.", "slug": "romy"},
    )
    html = client.get("/characters").text

    assert ">Now loves boats.</textarea>" in html
    assert "Loves trains." not in html


def test_dashboard_character_save_needs_a_name(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    html = client.post("/characters", data={"name": "  ", "background": "Loves trains."}).text

    assert "Fill in the required fields" in html
    assert "No characters yet" in html


def test_dashboard_stories_lists_characters_as_checkboxes(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    html = client.get("/stories").text

    assert "<legend>Characters</legend>" in html
    assert 'type="checkbox"' in html
    assert 'name="character"' in html
    assert 'value="romy"' in html
    assert ">Romy<" in html


def test_dashboard_keeps_selected_characters_on_the_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            characters=tmp_path / "characters",
            stories=tmp_path / "stories",
        )
    )
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    client.post("/characters", data={"name": "Baaba", "background": "Wears a hat."})
    client.post(
        "/stories",
        data={
            "story_title": "The little station",
            "character": ["romy"],
            "interests": "trains",
            "outline": "a ride",
        },
    )
    html = client.get("/stories").text

    assert 'value="romy" checked>' in html
    assert 'value="baaba">' in html
    assert 'value="baaba" checked>' not in html


def test_dashboard_story_ignores_character_slug_outside_the_pack(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    stories = tmp_path / "stories"
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=stories,
            characters=tmp_path / "characters",
        )
    )
    client.post(
        "/stories",
        data={"story_title": "The little station", "character": ["../secret", "romy"]},
    )
    notes = (stories / "the-little-station" / "story.yaml").read_text()

    assert "../secret" not in notes
    assert "romy" in notes


def test_dashboard_draft_uses_character_background(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    drafter = FakeDrafter(script="Rowmy waited at the station.")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            characters=tmp_path / "characters",
            stories=tmp_path / "stories",
            secrets=secrets,
            drafter=drafter,
        )
    )
    client.post("/characters", data={"name": "Romy", "background": "A small train-loving girl."})
    client.post(
        "/stories",
        data={"story_title": "The little station", "character": ["romy"], "outline": "a ride"},
    )
    client.post("/stories/draft")

    assert drafter.calls == [
        {
            "title": "The little station",
            "characters": "Romy: A small train-loving girl.",
            "interests": "",
            "outline": "a ride",
            "duration_seconds": "10",
        }
    ]


def test_dashboard_draft_shows_writing_in_progress(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    html = client.get("/stories").text

    assert 'action="/stories/draft"' in html
    assert "Writing the script" in html
    assert 'id="draft-status"' in html
    assert 'aria-live="polite"' in html
    assert "form-busy" in html


def test_dashboard_busy_script_disables_every_button_and_blocks_a_second_submit() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'document.querySelectorAll("button")' in html
    assert "preventDefault" in html
    assert "disabled = true" in html


def test_dashboard_stories_page_puts_write_form_above_saved_list() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text
    write = html.index("<h2>Write a story</h2>")
    saved = html.index("<h2>Saved stories</h2>")

    assert write < saved
    assert 'for="story-title"' in html


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
    assert "Open The little station" not in html


def test_dashboard_saved_stories_use_a_table_with_actions_on_the_right(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    listed = client.get("/stories").text.split("<h2>Saved stories</h2>", 1)[1]

    assert 'class="table-wrap"' in listed
    assert "<caption>Saved stories</caption>" in listed
    assert "<th>Title</th>" in listed
    assert "<th>Action</th>" in listed
    assert "<td>The little station</td>" in listed
    assert "Open The little station" not in listed
    assert listed.index("<td>The little station</td>") < listed.index(">Open<")
    assert listed.index(">Open<") < listed.index(">Delete<")


def test_dashboard_saved_stories_let_you_delete_not_speak(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    listed = client.get("/stories").text.split("<h2>Saved stories</h2>", 1)[1]

    assert 'action="/stories/speak"' not in listed
    assert ">Speak script<" not in listed
    assert 'name="voice_id"' not in listed
    assert 'action="/stories/delete"' in listed
    assert ">Delete<" in listed


def test_dashboard_speak_from_the_list_uses_that_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.story_audio import load_voices

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    speech = FakeSpeech(audio=b"ID3ok")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            speech=speech,
        )
    )
    client.post("/stories", data={"story_title": "Station", "script": "station script"})
    client.post("/stories", data={"story_title": "Helmet", "script": "helmet script"})
    client.post("/stories/speak", data={"slug": "station", "voice_id": load_voices()[0]["id"]})

    assert speech.calls == [{"text": "station script", "voice_id": load_voices()[0]["id"]}]


def test_dashboard_deletes_a_saved_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "outline": "a ride"})
    html = client.post("/stories/delete", data={"slug": "the-little-station"}).text

    assert "Open The little station" not in html
    assert "No saved stories yet" in html
    assert 'value="The little station"' not in html
    assert not (tmp_path / "the-little-station").exists()


def test_dashboard_new_story_clears_the_form(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post(
        "/stories",
        data={"story_title": "The little station", "outline": "a ride"},
    )
    saved = client.get("/stories").text
    html = client.post("/stories/new").text

    assert ">New story<" in saved
    assert saved.index(">New story<") < saved.index("<h2>Write a story</h2>")
    assert 'value="The little station"' not in html
    assert ">a ride</textarea>" not in html
    assert ">Open<" in html
    assert "The little station" in html


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

    assert ">one</textarea>" in html
    assert ">two</textarea>" not in html
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
            "elevenlabs_key": "sk_el-secret",
        },
    )
    html = client.get("/settings").text

    assert "gem-secret" not in html
    assert "sk_el-secret" not in html
    assert "Gemini key is set" in html
    assert "ElevenLabs key is set" in html
    text = secrets.read_text()
    assert "GEMINI_API_KEY=gem-secret" in text
    assert "ELEVENLABS_API_KEY=sk_el-secret" in text


def test_dashboard_settings_shows_masked_key_tails(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=sk-gemini-test-1a2b\nELEVENLABS_API_KEY=sk_eleven-test-9z8y\n")
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), secrets=secrets)).get("/settings").text

    assert "sk-gemini-test-1a2b" not in html
    assert "sk_eleven-test-9z8y" not in html
    assert "••••1a2b" in html
    assert "••••9z8y" in html


def test_dashboard_does_not_treat_an_elevenlabs_key_id_as_set(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n")
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), secrets=secrets)).get("/settings").text

    assert "ElevenLabs key is set" not in html
    assert "starts with sk_" in html


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
        duration_seconds: int = 10,
    ) -> str:
        self.calls.append(
            {
                "title": title,
                "characters": characters,
                "interests": interests,
                "outline": outline,
                "duration_seconds": str(duration_seconds),
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
            "duration_seconds": "10",
        }
    ]
    assert "gem-secret" not in html


def test_dashboard_draft_uses_saved_story_length(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    drafter = FakeDrafter(script="Rowmy waited at the station.")
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
        data={"story_title": "The little station", "duration_seconds": "240", "outline": "a ride"},
    )
    client.post("/stories/draft")

    assert drafter.calls[0]["duration_seconds"] == "240"


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
        def draft(
            self, *, title: str, characters: str, interests: str, outline: str, duration_seconds: int = 10
        ) -> str:
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
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\nELEVENLABS_VOICE_IDS=voice-a,voice-b\n")
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
    assert (tmp_path / "the-little-station" / "the-little-station.mp3").read_bytes() == b"ID3ok"
    assert "Spoken file: the-little-station.mp3" in html
    assert "the-little-station.mp3" in library
    assert speech.calls == [{"text": "Rowmy waited at the station. [pause]", "voice_id": "qXdtsJJ9LgnQ8Z2TYfav"}]
    assert "sk-secret" not in html


def test_dashboard_speak_links_the_library_track_back_to_the_story(tmp_path: Path) -> None:
    import yaml
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            speech=FakeSpeech(audio=b"ID3ok"),
        )
    )
    client.post(
        "/stories",
        data={"story_title": "The little station", "script": "Rowmy waited at the station."},
    )
    client.post("/stories/speak")
    notes = yaml.safe_load((tmp_path / "the-little-station" / "story.yaml").read_text())
    library = client.get("/library").text

    assert notes["spoken_file"] == "the-little-station.mp3"
    assert notes["library_path"] == "the-little-station.mp3"
    assert ">the-little-station.mp3 · The little station<" in library


def test_dashboard_speak_saves_the_spoken_file_as_a_unique_title_slug(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    storage = FakeStorage(free_bytes=1024, files={"the-little-station.mp3": b"earlier"})
    speech = FakeSpeech(audio=b"ID3ok")
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
        data={"story_title": "The little station", "script": "Rowmy waited at the station."},
    )
    html = client.post("/stories/speak").text

    assert storage.files["the-little-station.mp3"] == b"earlier"
    assert storage.files["the-little-station-2.mp3"] == b"ID3ok"
    assert (tmp_path / "the-little-station" / "the-little-station-2.mp3").read_bytes() == b"ID3ok"
    assert "Spoken file: the-little-station-2.mp3" in html
    assert "Spoken file: spoken.mp3" not in html


def test_dashboard_speak_uses_the_voice_you_picked(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.story_audio import load_voices

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
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


def test_dashboard_speak_rejects_an_elevenlabs_key_id(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n")
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
    html = client.post("/stories/speak").text

    assert "starts with sk_" in html
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
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\nELEVENLABS_VOICE_IDS=voice-a\n")
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
    assert (tmp_path / "the-little-station" / "the-little-station.mp3").read_bytes() == b"second"
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
    characters_page = client.get("/characters").text
    stories = client.get("/stories").text
    settings = client.get("/settings").text

    for page in (home, figures, library, characters_page, stories, settings):
        assert "<nav" in page
        assert 'href="/"' in page
        assert ">Home<" in page
        assert 'href="/figures"' in page
        assert ">Figures<" in page
        assert 'href="/library"' in page
        assert ">Library<" in page
        assert 'href="/characters"' in page
        assert ">Characters<" in page
        assert 'href="/stories"' in page
        assert ">Stories<" in page
        assert 'href="/write"' not in page
        assert ">Write<" not in page
        assert 'href="/settings"' in page
        assert ">Settings<" in page

    assert "<h2>Volume</h2>" not in home
    assert "<h2>Keys</h2>" not in home
    assert 'action="/assign"' not in home
    assert "<h2>Write a story</h2>" not in home
    assert "<h2>Saved stories</h2>" not in home
    assert "<h2>Add a character</h2>" not in home
    assert 'action="/assign"' not in figures
    assert 'action="/tracks"' not in figures
    assert 'action="/register-mode"' in figures
    assert 'action="/assign"' in library
    assert 'action="/tracks"' in library
    assert "<h2>Volume</h2>" not in figures
    assert "<h2>Add a character</h2>" in characters_page
    assert 'action="/characters"' in characters_page
    assert "<h2>Write a story</h2>" not in characters_page
    assert "<h2>Write a story</h2>" in stories
    assert "<h2>Saved stories</h2>" in stories
    assert "<legend>Characters</legend>" in stories
    assert 'action="/stories/draft"' not in stories
    assert "<h2>Keys</h2>" in settings
    assert 'for="play_mode"' in settings
    assert "<h2>Volume</h2>" in settings


def test_dashboard_settings_shows_empty_audit_log() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "<h2>Audit log</h2>" in html
    assert "Nothing has happened yet" in html


def test_dashboard_audit_log_copy_says_it_keeps_the_last_thousand_events() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "last 1000 events" in html
    assert "last 200 events" not in html


def test_dashboard_audit_log_lists_every_kept_event() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    for index in range(150):
        record_event(
            log,
            action="play",
            summary=f"event-{index}",
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/settings").text

    assert html.count('class="audit-log"') == 1
    assert html.count("<time ") == 150
    assert "event-0" in html
    assert "event-149" in html


def test_dashboard_settings_lists_audit_entries_newest_first() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    times = iter(
        [
            datetime(2026, 9, 19, 21, 0, tzinfo=UTC),
            datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
        ]
    )
    record_event(log, action="upload", summary="Stored frog.mp3", clock=lambda: next(times))
    record_event(log, action="play", summary="Played The Frog Prince", clock=lambda: next(times))

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/settings").text

    assert "Nothing has happened yet" not in html
    play = html.index("Played The Frog Prince")
    stored = html.index("Stored frog.mp3")
    assert play < stored
    assert "2026-09-19 21:01" in html
    assert 'datetime="2026-09-19T21:01:00+00:00"' in html


def test_dashboard_upload_records_the_audit_log() -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    log = MemoryAuditLog()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), catalog=FakeCatalog(), audit=log))
    client.post("/tracks", files={"file": ("frog.mp3", b"id3", "audio/mpeg")})

    html = client.get("/settings").text

    assert "Stored frog.mp3" in html


def test_dashboard_parent_changes_appear_in_the_audit_log(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.features.audit.memory import MemoryAuditLog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")
    secrets = tmp_path / "studio.env"
    stories = tmp_path / "stories"
    stories.mkdir()
    log = MemoryAuditLog()

    class Pad:
        def place(self, uid: str) -> None:
            return

    class Register:
        assign_mode = False

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(catalog_path),
            settings=SqliteSettings(tmp_path / "state.sqlite"),
            pad=Pad(),
            register=Register(),
            mixer=FakeMixer(level=10),
            stories=stories,
            secrets=secrets,
            audit=log,
        )
    )
    client.post(
        "/assign",
        data={"uid": "04aabbccddeeff", "path": "stories/frog-prince.mp3", "title": "The Frog Prince"},
    )
    client.post("/play-mode", data={"play_mode": "tap"})
    client.post("/volume", data={"step": "up"})
    client.post("/place/04aabbccddeeff")
    client.post("/present", data={"uid": "04aabbccddeeff"})
    client.post("/register-mode", data={"register": "on"})
    client.post("/tags/04aabbccddeeff/name", data={"name": "Frog"})
    client.post(
        "/stories",
        data={"story_title": "The station", "characters": "Romy", "interests": "trains", "outline": "a visit"},
    )
    client.post("/keys", data={"gemini_key": "gem-secret", "elevenlabs_key": "sk_el-secret"})

    html = client.get("/settings").text

    assert "Assigned The Frog Prince to 04aabbccddeeff" in html
    assert "Play mode set to tap" in html
    assert "Volume set to 11" in html
    assert "Placed 04aabbccddeeff" in html
    assert "Presented 04aabbccddeeff" in html
    assert "Register on" in html
    assert "Named 04aabbccddeeff Frog" in html
    assert "Saved story The station" in html
    assert "Saved studio keys" in html
    assert "gem-secret" not in html
    assert "sk_el-secret" not in html


def test_dashboard_draft_failure_shows_the_http_code_in_the_audit_log(tmp_path: Path) -> None:
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    class BoomDrafter:
        def draft(
            self, *, title: str, characters: str, interests: str, outline: str, duration_seconds: int = 10
        ) -> str:
            raise HTTPError(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini",
                429,
                "Too Many Requests",
                hdrs=None,
                fp=BytesIO(b""),
            )

    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            drafter=BoomDrafter(),
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station"})
    client.post("/stories/draft")

    html = client.get("/settings").text

    assert "Draft failed (429)" in html


def test_dashboard_speak_failure_shows_the_http_code_in_the_audit_log(tmp_path: Path) -> None:
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    class BoomSpeech:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            raise HTTPError(
                "https://api.elevenlabs.io/v1/text-to-speech/voice",
                401,
                "Unauthorized",
                hdrs=None,
                fp=BytesIO(b""),
            )

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            speech=BoomSpeech(),
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    client.post("/stories/speak")

    html = client.get("/settings").text

    assert "Speak failed (401)" in html


def test_dashboard_speak_failure_shows_the_elevenlabs_error_in_the_audit_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    quota = (
        "This request exceeds your API key (Vengeful Giant Otter) quota of 0. "
        "You have 0 credits remaining, while 595 credits are required for this request."
    )

    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/qXdtsJJ9LgnQ8Z2TYfav",
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(json.dumps({"detail": {"message": quota}}).encode()),
        )

    monkeypatch.setattr("romini.composition.story_audio.urlopen", fake_urlopen)
    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    client.post("/stories/speak")

    html = client.get("/settings").text

    assert quota in html


def test_dashboard_speak_shows_the_elevenlabs_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    quota = (
        "This request exceeds your API key (Vengeful Giant Otter) quota of 0. "
        "You have 0 credits remaining, while 595 credits are required for this request."
    )

    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/qXdtsJJ9LgnQ8Z2TYfav",
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(json.dumps({"detail": {"message": quota}}).encode()),
        )

    monkeypatch.setattr("romini.composition.story_audio.urlopen", fake_urlopen)
    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    html = client.post("/stories/speak").text

    assert quota in html


def test_dashboard_draft_shows_the_gemini_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    demand = (
        "This model is currently experiencing high demand. "
        "Spikes in demand are usually temporary. Please try again later."
    )

    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise HTTPError(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
            503,
            "Service Unavailable",
            hdrs=None,
            fp=BytesIO(json.dumps({"error": {"code": 503, "message": demand, "status": "UNAVAILABLE"}}).encode()),
        )

    monkeypatch.setattr("romini.composition.story_draft.urlopen", fake_urlopen)
    secrets = tmp_path / "studio.env"
    secrets.write_text("GEMINI_API_KEY=gem-secret\n")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
        )
    )
    client.post("/stories", data={"story_title": "The station", "outline": "a ride"})
    html = client.post("/stories/draft").text

    assert demand in html


def test_dashboard_speak_keeps_the_elevenlabs_error_after_another_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from io import BytesIO
    from urllib.error import HTTPError

    from fastapi.testclient import TestClient

    quota = (
        "This request exceeds your API key (Vengeful Giant Otter) quota of 0. "
        "You have 0 credits remaining, while 595 credits are required for this request."
    )

    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/qXdtsJJ9LgnQ8Z2TYfav",
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(json.dumps({"detail": {"message": quota}}).encode()),
        )

    monkeypatch.setattr("romini.composition.story_audio.urlopen", fake_urlopen)
    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=secrets,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    response = client.post("/stories/speak", follow_redirects=False)
    client.get("/library")
    html = client.get(response.headers["location"]).text

    assert response.status_code == 303
    assert quota in html


def test_dashboard_full_upload_appears_in_the_audit_log() -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=0),
            catalog=FakeCatalog(),
            audit=log,
        )
    )
    client.post("/tracks", files={"file": ("frog.mp3", b"id3", "audio/mpeg")})

    html = client.get("/settings").text

    assert "Could not store frog.mp3 (full)" in html


def test_dashboard_speak_full_disk_appears_in_the_audit_log(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=sk_secret\n")
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=0),
            catalog=FakeCatalog(),
            stories=tmp_path,
            secrets=secrets,
            speech=FakeSpeech(audio=b"ID3ok"),
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    client.post("/stories/speak")

    html = client.get("/settings").text

    assert "Speak failed (full)" in html


def test_dashboard_draft_without_a_key_appears_in_the_audit_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=tmp_path / "studio.env",
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station"})
    client.post("/stories/draft")

    html = client.get("/settings").text

    assert "Draft failed (no key)" in html


def test_dashboard_speak_without_a_key_appears_in_the_audit_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    log = MemoryAuditLog()
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=tmp_path,
            secrets=tmp_path / "studio.env",
            audit=log,
        )
    )
    client.post("/stories", data={"story_title": "The station", "script": "Once upon a time"})
    client.post("/stories/speak")

    html = client.get("/settings").text

    assert "Speak failed (no key)" in html


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
    assert 'href="/characters"' in html
    assert 'href="/write"' not in html


def test_dashboard_home_jump_list_includes_characters() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert '<a href="/characters"><strong>Characters</strong>' in html


def test_dashboard_home_shows_the_box_picture() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'src="/logo.svg"' in html
    assert 'class="welcome"' in html


def test_dashboard_home_shows_what_is_playing_now(tmp_path: Path) -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog-prince.mp3"\n'
        '    title: "The Frog Prince"\n'
        "tags:\n"
        "  - uid: 04aabbccddeeff\n"
        "    name: Frog\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/")
        .text
    )

    assert 'aria-label="Now playing"' in html
    assert 'aria-live="polite"' in html
    assert "<dl>" in html
    assert ">Story<" in html
    assert "The Frog Prince" in html
    assert ">Trigger<" in html
    assert "Frog" in html
    assert ">Time<" in html
    assert "22:33" in html


def test_dashboard_home_offers_pause_when_a_story_is_playing(tmp_path: Path) -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/")
        .text
    )

    assert 'action="/play"' in html
    assert ">Pause<" in html


def test_dashboard_play_pauses_when_a_story_is_playing() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    player = FakePlayer()
    player.play("stories/frog-prince.mp3", position_sec=0.0, uid="04aabbccddeeff")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player)).post(
        "/play",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?notice=paused"
    assert player.is_playing() is False
    assert player.pauses == 1


def test_dashboard_home_offers_play_when_the_story_is_paused(tmp_path: Path) -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Paused:
        def is_playing(self) -> bool:
            return False

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Paused(),
            )
        )
        .get("/")
        .text
    )

    assert 'aria-label="Now playing"' in html
    assert 'action="/play"' in html
    assert ">Play<" in html
    assert ">Pause<" not in html


def test_dashboard_home_hides_now_playing_when_the_box_is_quiet() -> None:
    from fastapi.testclient import TestClient

    class Quiet:
        def is_playing(self) -> bool:
            return False

        def playing_uid(self) -> str | None:
            return None

        def playing_path(self) -> str | None:
            return None

        def position_sec(self) -> float:
            return 0.0

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=Quiet())).get("/").text

    assert 'aria-label="Now playing"' not in html
    assert ">Story<" not in html


def test_dashboard_write_page_lets_you_pick_a_named_voice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text

    assert 'for="voice"' in html
    assert ">Voice<" in html
    assert 'name="voice_id"' in html
    assert 'action="/stories/speak"' in html


def test_dashboard_pages_live_in_the_dashboard_package() -> None:
    from romini.composition.dashboard import characters, figures, home, library, settings, stories

    assert Path(characters.__file__).name == "characters.py"
    assert Path(figures.__file__).name == "figures.py"
    assert Path(home.__file__).name == "home.py"
    assert Path(library.__file__).name == "library.py"
    assert Path(settings.__file__).name == "settings.py"
    assert Path(stories.__file__).name == "stories.py"


def test_dashboard_library_lets_you_listen_to_a_track() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )

    assert "<h2>Listen</h2>" in html
    assert 'for="preview"' in html
    assert ">Track<" in html
    assert 'id="preview"' in html
    assert 'value="/library/file/frog.mp3"' in html
    assert "<audio" in html
    assert "controls" in html
    assert 'id="player"' in html


def test_dashboard_serves_a_library_file_for_preview() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})
    response = TestClient(create_dashboard(storage=storage)).get("/library/file/frog.mp3")

    assert response.status_code == 200
    assert response.content == b"id3"
    assert response.headers["content-type"].startswith("audio/")


def test_dashboard_preview_rejects_a_path_outside_the_library() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})
    response = TestClient(create_dashboard(storage=storage)).get("/library/file/../frog.mp3")

    assert response.status_code == 404


def test_dashboard_preview_serves_a_nested_library_file() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024, files={"stories/frog.mp3": b"id3"})
    response = TestClient(create_dashboard(storage=storage)).get("/library/file/stories/frog.mp3")

    assert response.status_code == 200
    assert response.content == b"id3"


def test_dashboard_preview_player_is_labelled() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )

    assert 'aria-label="Preview"' in html
