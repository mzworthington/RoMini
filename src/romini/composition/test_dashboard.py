from dataclasses import dataclass, field
from pathlib import Path

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import DiskStorage, create_dashboard
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode


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


def test_dashboard_home_is_labelled_for_a_parent() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "<h1" in html
    assert "<main" in html
    assert "<label" in html
    assert 'for="uid"' in html
    assert 'for="path"' in html
    assert 'for="title"' in html
    assert 'for="file"' in html
    assert 'for="play_mode"' in html
    assert "<select" in html
    assert 'value="presence"' in html
    assert 'value="tap"' in html
    assert "free_bytes" not in html
    assert "bytes free" in html or "KB free" in html


def test_dashboard_home_has_upload_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert 'action="/tracks"' in response.text
    assert 'type="file"' in response.text


def test_dashboard_upload_file_is_required() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'id="file" type="file" name="file" accept="audio/*" required>' in html


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
    response = TestClient(app).get("/")

    assert 'action="/assign"' in response.text
    assert 'name="uid"' in response.text
    assert 'name="path"' in response.text
    assert 'name="title"' in response.text


def test_dashboard_assign_form_marks_required_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'id="uid" name="uid" required>' in html
    assert 'id="title" name="title" type="text" required>' in html
    assert 'id="path" name="path" required>' in html


def test_dashboard_assign_path_lists_library_files() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(
        free_bytes=1024,
        files={"frog.mp3": b"id3", "stories/frog-prince.mp3": b"id3"},
    )
    html = TestClient(create_dashboard(storage=storage)).get("/").text

    assert '<select id="path" name="path" required>' in html
    assert '<option value="frog.mp3">' in html
    assert '<option value="stories/frog-prince.mp3">' in html


def test_dashboard_assign_path_empty_when_library_has_no_files() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

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
    response = TestClient(app).get("/")

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
    response = TestClient(app).get("/")

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
    response = TestClient(app).get("/")

    assert "<table>" in response.text
    assert "<th>UID</th>" in response.text
    assert "<th>Title</th>" in response.text
    assert "<th>Path</th>" in response.text
    assert "stories/frog-prince.mp3" in response.text


def test_dashboard_home_lays_out_actions_in_a_flex_board_below_library() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'class="board"' in html
    library = html.index("<h2>Library</h2>")
    board = html.index('class="board"')
    upload = html.index("<h2>Upload a track</h2>")
    assert library < board < upload
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
    response = TestClient(app).get("/")

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
    response = TestClient(app).get("/")

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
    response = TestClient(app).get("/")

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
    assert response.headers["location"] == "/?notice=placed"
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
    assert response.headers["location"] == "/?notice=placed"


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
    assert response.headers["location"] == "/?notice=register-on"
    assert register.assign_mode is True


def test_dashboard_register_mode_off_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = True

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).post(
        "/register-mode", data={"register": "off"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?notice=register-off"


def test_dashboard_home_has_register_form() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = False

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/").text

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
        .get("/")
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
        .get("/")
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
    assert response.headers["location"] == "/?notice=named"


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
        .get("/")
        .text
    )

    assert 'action="/tags/04aabbccddeeff/name"' in html
    assert 'name="name"' in html
    assert 'for="tag-name-04aabbccddeeff"' in html


def test_dashboard_register_on_refreshes_home() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = True

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/").text

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

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/").text

    assert 'action="/present"' in html
    assert 'id="present-uid"' in html
    assert 'for="present-uid"' in html


def test_dashboard_present_uid_is_required() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/").text

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
    assert response.headers["location"] == "/?notice=presented"
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
    assert response.headers["location"] == "/?notice=presented"


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
    assert response.headers["location"] == "/?notice=assigned"


def test_dashboard_play_mode_form_returns_to_home_with_notice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)).post(
        "/play-mode", data={"play_mode": "tap"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?notice=play-mode"


def test_dashboard_upload_form_returns_to_home_with_notice() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024), catalog=FakeCatalog())
    response = TestClient(app).post(
        "/tracks",
        files={"file": ("frog.mp3", b"id3", "audio/mpeg")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?notice=uploaded"


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

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/favicon.svg")

    assert response.status_code == 200
    assert "image/svg" in response.headers["content-type"]
    assert b"#FF6B6B" in response.content
    assert b"#F7B731" in response.content


def test_dashboard_home_renders_from_jinja_template() -> None:
    from fastapi.testclient import TestClient

    from romini.composition import dashboard as dashmod

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    source = Path(dashmod.__file__).read_text()
    template = Path(dashmod.__file__).parent / "templates" / "home.html"

    assert template.is_file()
    assert "{{" in template.read_text()
    assert "<!DOCTYPE html>" not in source
    assert "DASHBOARD_STYLE" not in source
    assert "REGISTER_POLL" not in source
    assert "<main" in html
    assert "1.0 KB free" in html
