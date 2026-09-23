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
    volts: float | None = None
    flow: str | None = None


@dataclass
class FakeStorage:
    free_bytes: int
    files: dict[str, bytes] = field(default_factory=dict)
    total_bytes: int | None = None
    root: str = ""

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


def test_dashboard_aborted_upload_stays_quiet() -> None:
    import asyncio

    storage = FakeStorage(free_bytes=1024)
    app = create_dashboard(storage=storage)
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/tracks",
        "raw_path": b"/tracks",
        "query_string": b"",
        "headers": [
            (b"content-type", b"multipart/form-data; boundary=----romini"),
            (b"content-length", b"999999"),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    asyncio.run(app(scope, receive, send))

    assert sent[0]["type"] == "http.response.start"
    assert int(sent[0]["status"]) < 500
    assert storage.files == {}


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


def test_dashboard_live_player_is_playback_without_the_old_jump_list() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'class="page-title"' in html
    assert "Audio Deck &amp; Playback Stream" in html.split("<main", 1)[1]
    assert "Nothing is playing" in html
    assert 'class="jumps"' not in html
    assert "Toys" not in html
    assert ">Settings<" not in html


def test_dashboard_header_has_no_account_control() -> None:
    from fastapi.testclient import TestClient

    header = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
        .get("/")
        .text.split("<header", 1)[1]
        .split("</header>", 1)[0]
    )

    assert 'class="account"' not in header


def test_dashboard_header_matches_the_prototype_top_bar() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/")
        .text
    )
    header = html.split("<header", 1)[1].split("</header>", 1)[0]

    assert 'class="topbar"' in header
    assert header.index('class="masthead"') < header.index('aria-label="Dashboard"')
    assert header.index('aria-label="Dashboard"') < header.index('class="status-pills"')
    assert "1.0 KB free" not in header
    assert "72% charged" in header


def test_dashboard_home_renders_when_host_is_missing() -> None:
    from romini.composition.dashboard.shared import templates

    html = templates.get_template("layout.html").render(page="home", version="0")

    assert "Wi-Fi Not reported" in html


def test_dashboard_header_keeps_each_cluster_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    nav = html.split('nav[aria-label="Dashboard"] ul {\n  display: flex;', 1)[1].split("}", 1)[0]
    pills = html.split(".status-pills {", 1)[1].split("}", 1)[0]
    narrow = html.split("@media (max-width: 960px) {", 1)[1].split("@media", 1)[0]

    assert "flex-wrap: nowrap" in nav
    assert "flex-wrap: nowrap" in pills
    assert 'nav[aria-label="Dashboard"]' in narrow
    assert "flex: 1 0 100%" in narrow
    assert "overflow-x: auto" in narrow


def test_dashboard_header_pills_are_charge_cap_and_wifi() -> None:
    from fastapi.testclient import TestClient

    header = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72),
                mixer=FakeMixer(level=40, ceiling=75),
            )
        )
        .get("/")
        .text.split("<header", 1)[1]
        .split("</header>", 1)[0]
    )
    pills = header.split('class="status-pills"', 1)[1].split("</ul>", 1)[0]

    assert pills.index("72% charged") < pills.index("Cap 75")
    assert pills.index("Cap 75") < pills.index("Wi-Fi")
    assert "free" not in pills


def test_dashboard_live_player_is_a_playback_deck() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'class="deck ' in html
    assert "Nothing is playing" in html


def test_dashboard_live_player_matches_the_nordic_audio_deck() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'class="dock-ring"' in html
    assert 'class="waveform"' in html
    assert 'aria-label="Night light"' in html
    assert "Screen-free domestic audio for growing minds." in html
    assert "Nothing is playing" in html


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

    file_input = html.split('id="file"', 1)[1].split(">", 1)[0]
    assert 'type="file"' in file_input
    assert 'name="file"' in file_input
    assert 'accept="audio/*"' in file_input
    assert "multiple" in file_input
    assert "required" not in file_input


def test_dashboard_upload_form_has_a_folder_picker() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert '<label for="folder">Folder of tracks</label>' in html
    folder = html.split('id="folder"', 1)[1].split(">", 1)[0]
    assert "webkitdirectory" in folder
    assert "multiple" in folder
    assert "accept=" not in folder


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


def test_dashboard_library_page_matches_the_audio_library_layout() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert "MicroSD Capacity" in html
    assert "Total Audio Assets" in html
    assert "NFC Pairing" in html
    assert "DAC Configuration" in html
    assert "Drag audio files directly onto this panel" in html
    assert "Active Sync Queue" in html
    assert "Upload Audio Files" in html
    assert "Physical Figurine Link" in html
    assert "Browse Laptop Disk" in html
    assert 'class="card deck' not in html
    assert 'class="card scan-dock"' not in html


def test_dashboard_library_tracks_use_nordic_cards_and_an_empty_state() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="quota-cards"' in html
    assert html.count('class="card') >= 2
    assert "No stories yet. Upload a track, then assign a figure." in html
    assert 'for="file"' in html
    assert 'for="uid"' in html
    assert 'aria-label="Preview"' not in html


def test_dashboard_library_upload_and_queue_share_the_same_row_height() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    rule = html.split(".board:has(.drop) {", 1)[1].split("}", 1)[0]

    assert "align-items: stretch" in rule
    assert "grid-row: span 2" not in html


def test_dashboard_library_upload_sits_in_a_drop_well() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="card drop"' in html
    assert 'for="file"' in html
    assert 'for="folder"' in html


def test_dashboard_library_grid_lays_tracks_in_four_columns() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    rule = html.split(".library-catalog table.is-grid tbody {", 1)[1].split("}", 1)[0]

    assert "display: grid" in rule
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in rule


def test_dashboard_library_upload_well_takes_a_dropped_audio_file() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    well = html.split('id="upload-well"', 1)[1].split("</section>", 1)[0]

    assert well.index("Drag audio files directly onto this panel") < well.index('id="file"')
    assert 'addEventListener("drop"' in well
    drop = well.split('addEventListener("drop"', 1)[1]
    assert drop.index("input.files = event.dataTransfer.files") < drop.index("form.submit()")
    assert well.count('addEventListener("change"') == 2


def test_dashboard_library_upload_has_no_second_submit_button() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    form = html.split('id="upload-well"', 1)[1].split("</form>", 1)[0]

    assert "<button" not in form


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
    assert "<th>Physical Figurine Link</th>" in response.text
    assert "<th>Story Title</th>" in response.text
    assert "<th>Author / Narrator</th>" in response.text
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

    assert "<th>Physical Figurine Link</th>" in table
    assert "<th>UID</th>" not in table
    assert "Banana" in table
    assert "04aabbccddeeff" not in table


def test_dashboard_library_rows_lead_with_the_story_title(tmp_path: Path) -> None:
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
    head = table.split("</thead>", 1)[0]
    row = table.split("<tbody>", 1)[1]

    assert head.index("<th>Story Title</th>") < head.index("<th>Physical Figurine Link</th>")
    assert row.index('class="track-title"') < row.index('class="chip linked"')
    assert ">Romy and the banana<" in row
    assert ">Banana<" in row


def test_dashboard_library_catalog_table_matches_the_directory_design(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/gruffalo.mp3"

        def started_at(self) -> None:
            return None

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "The Gruffalo Figurine"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/gruffalo.mp3"\n'
        '    title: "The Gruffalo"\n'
        '    artist: "Julia Donaldson"\n'
        '  - path: "stories/caterpillar.mp3"\n'
        '    title: "The Very Hungry Caterpillar"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/library")
        .text
    )
    catalog = html.split('class="card library-catalog"', 1)[1].split('id="assign"', 1)[0]
    search_row = catalog.split('class="library-search-row"', 1)[1].split('class="filters"', 1)[0]

    assert 'id="q"' in search_row
    assert "Display Mode" in search_row
    assert 'aria-label="List view"' in search_row
    assert 'aria-label="Grid view"' in search_row
    assert catalog.index('class="filters"') < catalog.index('class="catalog-sheet"')
    playing = (
        catalog.split(">The Gruffalo<", 1)[0].rsplit("<tr", 1)[1]
        + catalog.split(">The Gruffalo<", 1)[1].split("</tr>", 1)[0]
    )
    waiting = catalog.split(">The Very Hungry Caterpillar<", 1)[1].split("</tr>", 1)[0]

    assert 'class="play-dot is-playing"' in playing
    assert "Active Preview" in playing
    assert 'class="credit-name"' in playing
    assert "Julia Donaldson" in playing
    assert 'class="chip linked"' in playing
    assert "The Gruffalo Figurine" in playing
    assert 'class="row-actions"' in playing
    assert 'aria-label="Upload cover"' in playing
    assert 'aria-label="Reassign figurine"' in playing
    assert "unlinked" in catalog.split(">The Very Hungry Caterpillar<", 1)[0].rsplit("<tr", 1)[1]
    assert 'class="chip missing"' in waiting
    assert "No Figurine Linked" in waiting
    assert 'class="link-tag"' in waiting
    assert "Link Tag" in waiting


def test_dashboard_active_preview_badge_stays_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    badge = html.split(".preview-badge {", 1)[1].split("}", 1)[0]

    assert "white-space: nowrap" in badge
    assert "flex-shrink: 0" in badge


def test_dashboard_library_row_shows_the_file_size_and_length(tmp_path: Path) -> None:
    import io
    import wave

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - path: "stories/romy.wav"\n    title: "Romy"\n')
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, files={"stories/romy.wav": buffer.getvalue()}),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library")
        .text
    )
    row = html.split("<tbody>", 1)[1].split("</tr>", 1)[0]

    assert "<th>Duration</th>" in html
    assert "<th>File Spec</th>" in html
    assert ">0:01<" in row
    assert ">15.7 KB<" in row


def test_dashboard_library_search_keeps_the_matching_title(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - path: "stories/banana.mp3"\n'
        '    title: "Romy and the banana"\n'
        '  - path: "stories/helmet.mp3"\n'
        '    title: "The helmet"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library?q=banana")
        .text
    )
    table = html[html.index("<tbody>") : html.index("</tbody>")]

    assert 'name="q"' in html
    assert 'value="banana"' in html
    assert "Romy and the banana" in table
    assert "The helmet" not in table


def test_dashboard_library_search_keeps_the_matching_figure(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Frog"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/picnic.mp3"\n'
        '    title: "A picnic"\n'
        '  - path: "stories/helmet.mp3"\n'
        '    title: "The helmet"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library?q=Frog")
        .text
    )
    table = html[html.index("<tbody>") : html.index("</tbody>")]

    assert "A picnic" in table
    assert "The helmet" not in table


def test_dashboard_library_can_show_only_tracks_with_no_figure(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Frog"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/picnic.mp3"\n'
        '    title: "A picnic"\n'
        '  - path: "stories/helmet.mp3"\n'
        '    title: "The helmet"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library?unassigned=1")
        .text
    )
    table = html[html.index("<tbody>") : html.index("</tbody>")]

    assert 'href="/library?unassigned=1"' in html
    assert "The helmet" in table
    assert "A picnic" not in table


def test_dashboard_library_row_says_when_no_figure_is_linked(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - path: "stories/romy.mp3"\n    title: "Romy"\n')
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
    row = html.split("<tbody>", 1)[1].split("</tr>", 1)[0]

    assert 'class="chip missing"' in row
    assert "No Figurine Linked" in row


def test_dashboard_library_studio_counts_tracks(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/romy.mp3"\n    title: "Romy"\n')
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
    counted = html.split("Total Audio Assets", 1)[1]

    assert 'class="studio"' in html
    assert ">1<" in counted[:80]


def test_dashboard_home_lays_out_actions_in_a_flex_board_below_library() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="board"' in html
    board = html.index('class="board"')
    upload = html.index("Drag audio files directly onto this panel")
    library = html.index('<h2 class="catalog-title">Library</h2>')
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


def test_dashboard_library_has_play_form_for_each_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=FakePlayer(),
            )
        )
        .get("/library")
        .text
    )

    assert 'action="/library/play/04aabbccddeeff"' in html
    assert ">Play<" in html


def test_dashboard_library_play_and_stop_records_todays_listening(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import DiskStorage, PathCatalog
    from romini.fakes import FakePlayer
    from romini.features.listening.log import MemoryPlayLog

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog.mp3"\n    title: "Frog"\n')
    log = MemoryPlayLog()
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            player=FakePlayer(),
            listening=log,
        )
    )

    client.post("/library/play/04aabbccddeeff", follow_redirects=False)
    client.post("/library/stop", follow_redirects=False)

    intervals = log.intervals()
    assert len(intervals) == 1
    assert intervals[0].ended_at is not None


def test_dashboard_next_track_opens_todays_listening(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import DiskStorage, PathCatalog
    from romini.fakes import FakePlayer
    from romini.features.listening.log import MemoryPlayLog

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog.mp3"\n    title: "Frog"\n')
    log = MemoryPlayLog()
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            player=FakePlayer(),
            listening=log,
        )
    )

    client.post("/play/next", follow_redirects=False)

    assert log.intervals()[0].ended_at is None


def test_dashboard_library_offers_stop_for_the_playing_track(tmp_path: Path) -> None:
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
            return datetime(2026, 9, 21, 6, 15)

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog-prince.mp3"\n'
        '    title: "The Frog Prince"\n'
        '  - uid: "04bbccddeeff00"\n'
        '    path: "stories/bear.mp3"\n'
        '    title: "Bear"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/library")
        .text
    )

    assert 'action="/library/stop"' in html
    assert ">Stop<" in html
    assert 'action="/library/play/04bbccddeeff00"' in html
    assert 'action="/library/play/04aabbccddeeff"' not in html


def test_dashboard_library_play_starts_the_mapped_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    library = tmp_path / "library"
    library.mkdir()
    (library / "stories").mkdir()
    (library / "stories" / "frog-prince.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    player = FakePlayer()
    response = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            settings=SqliteSettings(tmp_path / "state.sqlite"),
            player=player,
        )
    ).post("/library/play/04aabbccddeeff", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=playing"
    assert player.is_playing() is True
    assert player.playing_uid() == "04aabbccddeeff"
    assert player.plays == [(str(library / "stories" / "frog-prince.mp3"), 0.0)]


def test_dashboard_library_stop_stops_the_playing_track() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    player = FakePlayer()
    player.play("stories/frog-prince.mp3", position_sec=0.0, uid="04aabbccddeeff")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player)).post(
        "/library/stop",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=stopped"
    assert player.is_playing() is False
    assert player.stops == 1


def test_dashboard_library_play_replaces_the_running_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog-prince.mp3").write_bytes(b"id3")
    (library / "stories" / "bear.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog-prince.mp3"\n'
        '    title: "The Frog Prince"\n'
        '  - uid: "04bbccddeeff00"\n'
        '    path: "stories/bear.mp3"\n'
        '    title: "Bear"\n'
    )
    player = FakePlayer()
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            settings=SqliteSettings(tmp_path / "state.sqlite"),
            player=player,
        )
    )
    client.post("/library/play/04aabbccddeeff")
    response = client.post("/library/play/04bbccddeeff00", follow_redirects=False)

    assert response.status_code == 303
    assert player.stops == 1
    assert player.playing_uid() == "04bbccddeeff00"
    assert player.plays[-1] == (str(library / "stories" / "bear.mp3"), 0.0)


def test_dashboard_library_play_in_tap_mode_pauses_the_same_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog-prince.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    settings = SqliteSettings(tmp_path / "state.sqlite")
    settings.remember_play_mode(PlayMode.TAP)
    player = FakePlayer()
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            settings=settings,
            player=player,
        )
    )
    client.post("/library/play/04aabbccddeeff")
    response = client.post("/library/play/04aabbccddeeff", follow_redirects=False)

    assert response.status_code == 303
    assert player.pauses == 1
    assert player.is_playing() is False


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


def test_dashboard_scan_map_turns_nfc_register_off() -> None:
    from fastapi.testclient import TestClient

    class FakeRegister:
        assign_mode = True

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/figures").text
    )
    scan = html.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]

    assert "<h2>Register figures</h2>" not in html
    assert 'name="register" value="off"' in scan
    assert "Stop registering" in scan


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

    scan = html.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]
    assert 'action="/register-mode"' in scan
    assert 'name="register" value="on"' in scan
    assert "Register Detected Token" in scan
    assert "<h2>Register figures</h2>" not in html


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


def test_dashboard_named_figures_are_cards_not_a_table(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tags:\n  - uid: 04aabbccddeeff\n    name: Frog\ntracks: []\n")
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

    assert 'class="figure"' in html
    assert 'for="tag-name-04aabbccddeeff"' in html
    assert "<table>" not in html


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
    assert "data-poll" in html
    assert "setInterval" in html
    assert "2000" in html
    assert "location.reload" not in html
    assert "activeElement" in html
    assert "defaultValue" in html
    assert 'querySelectorAll("input, textarea, select")' in html


def test_dashboard_figures_page_leaves_plate_reads_to_the_sim_harness() -> None:
    from fastapi.testclient import TestClient

    class FakePad:
        def place(self, uid: str) -> None:
            return

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/figures").text

    assert "<h2>Present a figure</h2>" not in html
    assert 'action="/present"' not in html
    assert 'id="present-uid"' not in html


def test_dashboard_home_shows_notice_after_action() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text

    assert 'role="status"' in html
    assert "Figure assigned" in html


def test_dashboard_notice_overlays_the_page_and_can_dismiss() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text
    main = html.split("<main>", 1)[1].split("</main>", 1)[0]

    assert 'class="toast"' in html
    assert "data-toast" in html
    assert 'aria-label="Dismiss"' in html
    assert "Figure assigned" not in main
    assert "4200" in html


def test_dashboard_notices_stack_until_each_is_dismissed() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text

    assert 'class="toast-stack"' in html
    assert "data-toast-template" in html
    assert "appendChild" in html
    assert 'closest("[data-toast]")' in html


def test_dashboard_actions_swap_the_page_without_a_reload() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "history.pushState" in html
    assert "new DOMParser" in html
    assert "new FormData" in html
    assert "location.reload" not in html


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

    assert "#D97706" in html
    assert "#F9F7F2" in html
    assert "Plus Jakarta Sans" in html
    assert "Nunito" not in html
    assert "Quicksand" not in html
    assert 'url("/plus-jakarta-sans.woff2")' in html or "url(/plus-jakarta-sans.woff2)" in html
    assert 'src="/mark.svg"' in html
    assert 'href="/favicon.svg"' in html
    assert "Storybox" in html


def test_dashboard_does_not_fetch_fonts_from_the_internet() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


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


def test_dashboard_hardware_shows_percent_volume_studio_keys_and_box_facts() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                mixer=FakeMixer(level=10),
                battery=FakeBattery(percent=72),
            )
        )
        .get("/settings")
        .text
    )

    assert "<h2>Studio keys</h2>" in html
    assert "software ceiling" not in html.lower()
    assert "10 of 100" in html
    assert "72% charged" in html
    assert "1.0 KB free" in html
    assert 'for="volume-level"' in html
    assert 'for="gemini-key"' in html
    assert 'for="play_mode"' in html
    assert html.count('class="card"') >= 4


def test_dashboard_hardware_lays_care_out_as_pods() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )

    assert 'class="hw-care"' in html
    care = html.split('class="hw-care"', 1)[1]
    assert care.index("Studio keys") < care.index("Play mode")
    assert care.index("Audit log") > care.index("Play mode")
    assert "Firmware" not in care


def test_dashboard_hardware_studio_puts_box_facts_above_the_care_cards() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72),
            )
        )
        .get("/settings")
        .text
    )
    facts = html.split('class="studio"', 1)[1].split('class="hw-care"', 1)[0]

    assert "Charged" in facts
    assert ">72%<" in facts
    assert "Free on the box" in facts


def test_dashboard_settings_shows_the_pn532_on_spi() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "SPI0" in html
    assert "BCM 4" in html
    assert "BCM 20" in html
    assert "250 ms" in html
    assert "NTAG203" in html
    assert "0x24" not in html
    assert "HiFiBerry" not in html


def test_dashboard_settings_shows_the_analogue_player() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )

    assert "ALSA Headphones" in html
    assert "mpv.sock" in html
    assert "Cap 100" in html


def test_dashboard_settings_shows_host_load_memory_and_disk(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
        },
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(
                    free_bytes=4 * 1024 * 1024 * 1024,
                    total_bytes=28 * 1024 * 1024 * 1024,
                    root="/var/lib/romini",
                )
            )
        )
        .get("/settings")
        .text
    )

    assert "42°C" in html
    assert "Load 0.24" in html
    assert "612 MB / 3891 MB" in html
    assert "4.0 GB free" in html
    assert "28.0 GB" in html
    assert "/var/lib/romini" in html


def test_dashboard_host_card_draws_ram_and_disk_meters(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
        },
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(
                    free_bytes=4 * 1024 * 1024 * 1024,
                    total_bytes=28 * 1024 * 1024 * 1024,
                    root="/var/lib/romini",
                )
            )
        )
        .get("/settings")
        .text
    )
    card = html.split("Host node", 1)[1].split("<h2>Reader</h2>", 1)[0]

    assert "42°C" in card
    assert "Load 0.24" in card
    assert "612 MB / 3891 MB" in card
    assert 'style="width: 16%"' in card
    assert 'style="width: 86%"' in card
    assert "/var/lib/romini" in card


def test_dashboard_subsystem_cards_use_the_hardware_labels() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=84, volts=4.12, flow="charging"),
                mixer=FakeMixer(level=40, ceiling=75),
            )
        )
        .get("/settings")
        .text
    )

    assert "Proximity sensor" in html
    assert "Acoustic pipeline" in html
    assert "Telemetry unit" in html
    assert "SPI0" in html
    assert "NTAG203" in html
    assert "ALSA Headphones" in html
    assert "mpv.sock" in html
    assert "UPS HAT (D)" in html
    assert "21700" in html
    assert "4.12 V" in html
    assert "HiFiBerry" not in html
    assert "18650" not in html


def test_dashboard_hardware_skips_the_summary_strip() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/settings")
        .text
    )

    assert 'class="metrics"' not in html
    assert "Free on the box" in html
    assert "Charged" in html
    assert ">72%<" in html


def test_dashboard_network_card_names_remote_access() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    card = (
        html.split("<h2>Network</h2>", 1)[0].rsplit("<section", 1)[1]
        + html.split("<h2>Network</h2>", 1)[1].split("</section>", 1)[0]
    )

    assert "Remote access" in card
    assert "Not reported" in card
    assert "sudo nmtui" in card


def test_dashboard_hardware_keeps_labels_clear_of_their_values() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, root="/var/lib/romini"),
                mixer=FakeMixer(level=10),
            )
        )
        .get("/settings")
        .text
    )
    host = html.split("Host node", 1)[1].split("<h2>Reader</h2>", 1)[0]
    player = html.split("Acoustic pipeline", 1)[1].split("<h2>Pack</h2>", 1)[0]
    care = html.split('class="hw-care"', 1)[1]
    pair = care.split('class="hw-pair"', 1)[1].split('id="audit"', 1)[0]

    assert 'class="mount"' in host
    assert host.index(">Mount<") < host.index("/var/lib/romini")
    assert player.index("</p>") < player.index("Analogue jack")
    assert "Studio keys" in pair
    assert "Play mode" in pair
    assert "Audit log" not in pair


def test_dashboard_settings_names_the_box_on_the_title_line(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "romini",
            "address": "192.168.1.140",
            "cpu_temp": "42°C",
            "load": "0.24",
            "memory": "612 MB / 3891 MB",
            "uptime": "4d 12h",
            "wifi": "Not reported",
        },
    )
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    head = html.split('class="page-head"', 1)[1].split('class="page-actions"', 1)[0]

    assert "romini.local" in head
    assert "192.168.1.140" in head
    assert "4d 12h" in head
    assert "Raspberry Pi 4 Model B" in head
    assert "4GB" in head
    assert "System Healthy" not in html


def test_dashboard_mdns_name_keeps_a_single_local_suffix(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "romini.composition.dashboard.shared.read_host_facts",
        lambda: {
            "hostname": "Matthews-MacBook-Air.local",
            "address": "10.5.0.2",
            "cpu_temp": "Not reported",
            "load": "1.70",
            "memory": "Not reported",
            "uptime": "Not reported",
            "wifi": "Not reported",
        },
    )
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "Matthews-MacBook-Air.local.local" not in html
    assert "Matthews-MacBook-Air.local (10.5.0.2)" in html
    assert "ssh Matthews-MacBook-Air.local\n" in html


def test_dashboard_hardware_owns_the_chime_and_bedtime_sleep(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            mixer=FakeMixer(level=40, ceiling=75),
            settings=SqliteSettings(tmp_path / "state.sqlite"),
        )
    )
    home = client.get("/").text
    hardware = client.get("/settings").text
    safety = hardware.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert 'aria-label="Raspberry Pi safety"' not in home
    assert 'action="/safety/beep"' not in home
    assert 'action="/safety/sleep"' not in home
    assert "Stop &amp; Eject" in home
    assert "Volume cap" in home
    assert 'action="/volume"' in safety
    assert 'action="/safety/beep"' in safety
    assert 'action="/safety/sleep"' in safety
    assert "Sleep in 30m" in safety
    assert "dB" not in safety


def test_dashboard_hardware_puts_safety_beside_the_network() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10)))
        .get("/settings")
        .text
    )
    left = html.split('class="hw-main"', 1)[1].split('class="hw-side"', 1)[0]
    side = html.split('class="hw-side"', 1)[1].split('class="hw-care"', 1)[0]
    care = html.split('class="hw-care"', 1)[1]

    assert left.index("Parental audio safety") < left.index("Firmware")
    assert side.index("Network") < side.index('aria-label="On the plate"')
    assert care.index("Studio keys") < care.index("Play mode")
    assert care.index("Play mode") < care.index("Audit log")


def test_dashboard_settings_names_the_ups_hat() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), battery=FakeBattery(percent=72)))
        .get("/settings")
        .text
    )

    assert "UPS HAT (D)" in html
    assert "21700" in html
    assert "18650" not in html


def test_dashboard_settings_shows_pack_voltage() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72, volts=4.12),
            )
        )
        .get("/settings")
        .text
    )

    assert "4.12 V" in html
    assert "Pack voltage is not reported" not in html


def test_dashboard_settings_shows_whether_the_pack_is_charging() -> None:
    from fastapi.testclient import TestClient

    def page(flow: str) -> str:
        return (
            TestClient(
                create_dashboard(
                    storage=FakeStorage(free_bytes=1024),
                    battery=FakeBattery(percent=72, flow=flow),
                )
            )
            .get("/settings")
            .text
        )

    assert "Charging" in page("charging")
    assert "Discharging" in page("discharging")


def test_dashboard_hardware_names_the_figure_on_the_plate(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 0.0

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
        .get("/settings")
        .text
    )
    dock = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]

    assert ">Frog<" in dock
    assert "The Frog Prince" in dock


def test_dashboard_dock_shows_the_tag_and_safety_uses_panels(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 0.0

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
                mixer=FakeMixer(level=40, ceiling=75),
                settings=SqliteSettings(tmp_path / "state.sqlite"),
            )
        )
        .get("/settings")
        .text
    )
    dock = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]
    safety = html.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert "Figure present" in dock
    assert "04aabbccddeeff" in dock
    assert safety.count('class="safety-panel"') == 2
    assert safety.index('class="safety-panel"') < safety.index('action="/volume"')
    assert "Sleep in 30m" in safety.split('class="safety-panel"', 2)[2]
    assert 'class="safety-row"' in safety
    assert "dB" not in safety


def test_dashboard_hardware_shows_when_the_update_check_skipped(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "22 September 2026 at 10:04", "result": "skipped"}')
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), update_status=status)).get("/settings").text
    )

    assert "Last checked 22 September 2026 at 10:04." in html
    assert "skipped the install because a story was playing" in html
    assert "Story was playing" in html
    assert "romini-update.timer" in html
    assert "systemctl" not in html
    assert 'action="/update"' not in html


def test_dashboard_settings_shows_the_firmware_update_center(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "22 September 2026 at 03:15", "result": "current"}')
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), update_status=status)).get("/settings").text
    )
    center = html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]

    assert "Firmware &amp; OTA Update Center" in center
    assert "Official GitHub wheel distribution channel" in center
    assert "Up to date" in center
    assert "Current Build" in center
    assert "Update Channel" in center
    assert "mzworthington/RoMini" in center
    assert "Last Check Timer" in center
    assert "22 September 2026 at 03:15" in center
    assert "romini-update.timer" in center
    assert "Check for Updates Now" in center
    assert "Recent Installation Ledger" in center
    assert "The player is already up to date." in center


def test_dashboard_update_channel_stays_inside_its_card() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    center = html.split('id="firmware-update"', 1)[1]
    channel_value = center.split("Update Channel", 1)[1].split("</div>", 1)[0]
    columns = html.split(".firmware-facts {", 1)[1].split("}", 1)[0]
    channel = html.split(".firmware-facts dd.channel {", 1)[1].split("}", 1)[0]
    value = html.split(".firmware-facts dd {", 1)[1].split("}", 1)[0]

    assert 'class="channel"' in channel_value

    assert "minmax(18rem, 1fr)" in columns
    assert "white-space: nowrap" in channel
    assert "overflow-wrap: anywhere" not in value


def test_dashboard_firmware_center_shows_the_update_and_refresh_icons() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    center = html.split('id="firmware-update"', 1)[1].split("</section>", 1)[0]
    head = center.split("<h2", 1)[0]
    check = center.split("Check for Updates Now", 1)[0]

    assert 'class="firmware-mark"' in head
    assert 'class="refresh-mark"' in check


def test_dashboard_check_for_updates_starts_the_updater() -> None:
    from fastapi.testclient import TestClient

    class Updates:
        def __init__(self) -> None:
            self.checked = False

        def check(self) -> None:
            self.checked = True

    updates = Updates()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), updates=updates))
    html = client.get("/settings").text

    assert 'action="/system/update"' in html
    response = client.post("/system/update", follow_redirects=False)

    assert response.status_code == 303
    assert updates.checked is True
    assert "Update check started" in client.get("/settings?notice=update").text


def test_pi_update_check_starts_the_nightly_service(monkeypatch) -> None:
    from romini.composition.dashboard.power import LocalUpdate

    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.dashboard.power.subprocess.run", run)
    LocalUpdate(profile="pi").check()

    assert calls == [["systemctl", "start", "romini-update.service"]]


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
    assert ">Draft Script with Gemini<" in html
    assert 'action="/stories/speak"' in html
    assert ">Speak Script with ElevenLabs<" in html


def test_dashboard_draft_sits_under_save_in_the_write_section(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    empty = client.get("/stories").text

    assert 'action="/stories/draft"' not in empty
    assert ">Draft script<" not in empty

    client.post("/stories", data={"story_title": "The little station"})
    html = client.get("/stories").text
    write = html.split("<h2>Write a story</h2>", 1)[1].split("<h2>Saved stories</h2>", 1)[0]

    assert write.index(">Save Blueprint<") < write.index('action="/stories/draft"')
    assert write.index('action="/stories/draft"') < write.index("</section>")
    assert "#script" in html
    assert "min-height: 22rem" in html


def test_story_studio_compose_buttons_follow_the_design(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text
    write = html.split("<h2>Write a story</h2>", 1)[1].split("<h2>Saved stories</h2>", 1)[0]
    speak = html.split('action="/stories/speak"', 1)[1].split("</form>", 1)[0]

    assert ">Save Blueprint<" in write
    save = write.split(">Save Blueprint<", 1)[0].rsplit("<button", 1)[-1]
    draft = write.split(">Draft Script with Gemini<", 1)[0].rsplit("<button", 1)[-1]
    spoken = speak.split(">Speak Script with ElevenLabs<", 1)[0].rsplit("<button", 1)[-1]
    assert "soft-pill" not in save
    assert "soft-pill" not in draft
    assert "soft-pill" not in spoken
    assert ">Draft Script with Gemini<" in write
    assert 'class="spark-glyph"' in write
    assert ">Speak Script with ElevenLabs<" in speak
    assert 'class="voice-glyph"' in speak


def test_story_studio_keeps_space_under_the_metric_row() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text
    rule = html.split(".story-studio {", 1)[1].split("}", 1)[0]

    assert "flex-direction: column" in rule
    assert "gap: 1.15rem" in rule


def test_story_studio_action_buttons_stay_label_sized(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text
    glyphs = html.split(".spark-glyph", 1)[1].split("}", 1)[0]
    buttons = html.split(".story-studio section.card > form > button", 1)[1].split("}", 1)[0]

    assert ".voice-glyph" in glyphs
    assert "width: 1.05rem" in glyphs
    assert "height: 1.05rem" in glyphs
    assert "align-self: flex-start" in buttons
    assert "width: fit-content" in buttons


def test_dashboard_saved_stories_empty_when_none_saved(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path)).get("/stories").text

    assert "<h2>Saved stories</h2>" in html
    assert "No saved stories yet" in html


def test_story_studio_is_one_page_for_writing_and_characters() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))

    for path in ("/stories", "/characters"):
        html = client.get(path).text
        assert '<h2 class="page-title">Bedtime Story Studio &amp; Characters</h2>' in html
        assert 'class="story-studio"' in html
        assert 'for="story-title"' in html
        assert 'for="character-name"' in html
        assert "<h2>Write a story</h2>" in html
        assert "<h2>Add a character</h2>" in html
        primary = html.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]
        studio = primary.split('href="/stories"', 1)[1].split("</a>", 1)[0]
        assert "Story Studio" in studio
        assert 'aria-current="page"' in studio
        assert 'aria-label="Library"' not in html


def test_story_studio_header_actions_follow_the_design() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text
    actions = html.split('class="page-actions studio-toolbar"', 1)[1].split("<main", 1)[0]

    assert "Gemini 3.6 Flash" in actions
    assert "ElevenLabs v3" in actions
    assert ">API Keys<" in actions
    assert 'class="key-glyph"' in actions
    assert ">New Character<" in actions
    assert 'class="person-glyph"' in actions
    assert ">Create New Story<" in actions
    assert 'class="plus-glyph"' in actions


def test_dashboard_scan_tag_stays_on_one_line_and_system_nav_names_hardware() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    primary = html.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]
    scan = html.split(".scan {", 1)[1].split("}", 1)[0]

    assert ">System &amp; Hardware<" in primary
    assert "white-space: nowrap" in scan
    assert "flex: none" in scan


def test_dashboard_primary_nav_is_live_player_figures_library_and_hardware() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
    primary = client.get("/").text.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]

    assert ">Live Player<" in primary
    assert ">Figures &amp; Tags<" in primary
    assert ">Audio Library<" in primary
    assert ">System &amp; Hardware<" in primary
    assert ">Home<" not in primary
    assert ">Settings<" not in primary
    assert ">Stories<" not in primary
    assert ">Characters<" not in primary
    assert '<nav aria-label="Library">' not in client.get("/library").text


def test_dashboard_story_bookmarks_keep_library_current_and_the_studio() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))

    for path in ("/stories", "/characters"):
        html = client.get(path).text
        primary = html.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]
        assert 'aria-current="page"' in primary.split(">Story Studio<", 1)[0]
        assert ">Stories<" not in primary
        assert ">Characters<" not in primary
        assert 'aria-label="Library"' not in html

    stories = client.get("/stories").text
    assert "<legend>Characters</legend>" in stories
    assert "<h2>Write a story</h2>" in stories
    assert "<h2>Add a character</h2>" in client.get("/characters").text


def test_dashboard_story_pages_name_themselves_like_the_other_destinations() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))

    title = '<h2 class="page-title">Bedtime Story Studio &amp; Characters</h2>'
    assert title in client.get("/stories").text
    assert title in client.get("/characters").text


def test_dashboard_nav_has_stories_without_a_separate_write_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text

    assert 'href="/stories"' in html
    assert ">Story Studio<" in html
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


def test_story_studio_character_roster_follows_the_design(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    roster = client.get("/characters").text.split('id="characters"', 1)[1].split("<h2>Saved stories</h2>", 1)[0]

    assert "Family Characters (1)" in roster
    assert "fed to Gemini" in roster
    assert 'class="roster-mark"' in roster
    assert 'class="roster-add"' in roster
    assert 'class="avatar avatar-0"' in roster
    assert 'href="/characters/romy"' in roster


def test_character_editor_opens_from_new_or_edit_and_cancel_closes_it(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    studio = client.get("/stories").text

    assert 'id="character-form" hidden' in studio
    assert '<form class="roster-add" action="/characters/new" method="post">' in studio

    editing = client.get("/characters/romy").text
    assert 'id="character-form" hidden' not in editing
    assert 'value="Romy"' in editing
    editor = editing.split('id="character-form"', 1)[1]
    assert ">Cancel<" in editor
    assert 'href="/stories"' in editor.split(">Cancel<", 1)[0]

    adding = client.post("/characters/new").text
    assert 'id="character-form" hidden' not in adding
    assert "<h2>Add a character</h2>" in adding
    assert 'value="Romy"' not in adding

    closed = client.get("/stories").text
    assert 'id="character-form" hidden' in closed


def test_dashboard_saved_characters_are_cards_not_a_table(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    html = client.get("/characters").text

    assert 'class="character"' in html
    assert "<table>" not in html
    assert 'href="/characters/romy"' in html


def test_dashboard_characters_studio_counts_saved_characters(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    html = client.get("/characters").text
    counted = html.split("Characters saved", 1)[1]

    assert 'class="studio"' in html
    assert ">1<" in counted[:80]


def test_dashboard_saved_character_has_a_shareable_url(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    saved = client.post(
        "/characters",
        data={"name": "Romy", "background": "Loves trains."},
        follow_redirects=False,
    )

    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/characters/romy")
    html = client.get("/characters/romy").text
    assert 'value="Romy"' in html
    assert ">Loves trains.</textarea>" in html


def test_dashboard_characters_index_redirects_to_the_saved_name(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    listed = client.get("/characters", follow_redirects=False)

    assert listed.status_code == 303
    assert listed.headers["location"].startswith("/characters/romy")


def test_dashboard_opening_a_character_fills_the_form(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    client.post("/characters/open", data={"slug": "romy"})
    html = client.get("/characters").text

    assert 'value="Romy"' in html
    assert ">Loves trains.</textarea>" in html
    assert ">Edit<" in html


def test_dashboard_saved_character_open_is_a_shareable_link(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), characters=tmp_path))
    client.post("/characters", data={"name": "Romy", "background": "Loves trains."})
    listed = client.get("/characters").text.split("Family Characters", 1)[1]

    assert 'href="/characters/romy"' in listed
    assert 'action="/characters/open"' not in listed


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

    assert ">New Character<" in saved
    assert saved.index(">New Character<") < saved.index("<h2>Edit a character</h2>")
    assert 'value="Romy"' not in html
    assert 'type="hidden" name="slug"' not in html
    assert ">Edit<" in html


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


def test_dashboard_saved_story_has_a_shareable_url(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    saved = client.post("/stories", data={"story_title": "The little station"}, follow_redirects=False)

    assert saved.status_code == 303
    assert saved.headers["location"].startswith("/stories/the-little-station")
    html = client.get("/stories/the-little-station").text
    assert 'value="The little station"' in html


def test_dashboard_stories_studio_counts_saved_stories(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text
    counted = html.split("Stories saved", 1)[1]

    assert 'class="studio"' in html
    assert ">1<" in counted[:80]


def test_dashboard_stories_index_redirects_to_the_saved_title(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    listed = client.get("/stories", follow_redirects=False)

    assert listed.status_code == 303
    assert listed.headers["location"].startswith("/stories/the-little-station")


def test_dashboard_saved_stories_use_a_table_with_actions_on_the_right(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    listed = client.get("/stories").text.split("<h2>Saved stories</h2>", 1)[1]

    assert 'class="story-stack"' in listed
    assert 'class="track-title"' in listed
    assert "Open The little station" not in listed
    assert listed.index('class="track-title"') < listed.index(">Open<")
    assert listed.index(">Open<") < listed.index(">Delete<")


def test_dashboard_saved_story_rows_lead_with_the_title(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    listed = client.get("/stories").text.split("<h2>Saved stories</h2>", 1)[1]

    assert listed.index('class="track-title"') < listed.index(">Open<")
    assert "The little station" in listed.split('class="track-title"', 1)[1].split("</span>", 1)[0]


def test_dashboard_saved_story_open_is_a_shareable_link(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    listed = client.get("/stories").text.split("<h2>Saved stories</h2>", 1)[1]

    assert 'href="/stories/the-little-station"' in listed
    assert 'action="/stories/open"' not in listed


def test_dashboard_saved_story_open_looks_like_a_button(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station"})
    html = client.get("/stories").text
    listed = html.split("<h2>Saved stories</h2>", 1)[1]

    assert '<a class="button" href="/stories/the-little-station">Open</a>' in listed
    assert "a.button" in html


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

    assert ">Create New Story<" in saved
    assert saved.index(">Create New Story<") < saved.index("<h2>Write a story</h2>")
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

    assert "<h2>Studio keys</h2>" in html
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
        primary = page.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]
        assert ">Live Player<" in primary
        assert ">Home<" not in primary
        assert ">Figures &amp; Tags<" in primary
        assert ">Audio Library<" in primary
        assert ">Story Studio<" in primary
        assert ">System &amp; Hardware<" in primary
        assert ">Settings<" not in primary
        assert 'href="/write"' not in page
        assert ">Write<" not in page
        assert '<nav aria-label="Library">' not in page

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
    assert "<h2>Write a story</h2>" in characters_page
    assert "<h2>Write a story</h2>" in stories
    assert "<h2>Saved stories</h2>" in stories
    assert "<legend>Characters</legend>" in stories
    assert 'action="/stories/draft"' not in stories
    assert "<h2>Studio keys</h2>" in settings
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


def test_dashboard_activity_stream_shows_a_headline_and_a_description() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    record_event(
        log,
        action="place",
        headline="The Gruffalo placed",
        summary="Story started from the saved bookmark.",
        clock=lambda: datetime(2026, 9, 19, 14, 22, tzinfo=UTC),
    )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/figures").text
    item = html.split('<ul class="activity">', 1)[1].split("</ul>", 1)[0]

    assert "<strong>The Gruffalo placed</strong>" in item
    assert "<p>Story started from the saved bookmark.</p>" in item
    assert item.index("<strong>The Gruffalo placed</strong>") < item.index(
        "<p>Story started from the saved bookmark.</p>"
    )


def test_dashboard_activity_stream_uses_the_action_when_a_row_has_no_headline() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    record_event(
        log,
        action="place",
        summary="Placed 04aabbccddeeff",
        clock=lambda: datetime(2026, 9, 19, 14, 22, tzinfo=UTC),
    )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/figures").text

    assert "<strong>Place</strong>" in html
    assert "<p>Placed 04aabbccddeeff</p>" in html


def test_dashboard_activity_stream_is_a_short_live_preview_of_the_journal() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    for index, minute in enumerate(range(6)):
        record_event(
            log,
            action="place",
            headline=f"Event {index}",
            summary=f"Detail {index}",
            clock=lambda minute=minute: datetime(2026, 9, 19, 14, minute, tzinfo=UTC),
        )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/figures").text
    stream = html.split('<ul class="activity">', 1)[1].split("</ul>", 1)[0]

    assert "Activity Stream" in html
    assert "Live FIFO" in html
    assert '<time datetime="2026-09-19T14:05:00+00:00">14:05</time>' in stream
    assert "2026-09-19 14:05" not in stream
    assert stream.count("activity-mark") == 4
    assert "Event 5" in stream
    assert "Event 1" not in stream
    assert 'href="/settings#audit"' in html
    assert "View Complete Hardware Journal" in html


def test_dashboard_activity_stream_skips_a_description_that_repeats_the_headline() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    record_event(
        log,
        action="register",
        headline="Register off",
        summary="Register off",
        clock=lambda: datetime(2026, 9, 23, 7, 13, tzinfo=UTC),
    )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/figures").text
    item = html.split('<ul class="activity">', 1)[1].split("</ul>", 1)[0]

    assert "<strong>Register off</strong>" in item
    assert "<p>" not in item


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


def test_dashboard_audit_log_shows_a_headline_and_a_description() -> None:
    from datetime import UTC, datetime

    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog
    from romini.features.audit.record import record_event

    log = MemoryAuditLog()
    record_event(
        log,
        action="play",
        headline="Story playing",
        summary="Played The Frog Prince",
        clock=lambda: datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
    )

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), audit=log)).get("/settings").text
    item = html.split('<ol class="audit-log">', 1)[1].split("</ol>", 1)[0]

    assert "<strong>Story playing</strong>" in item
    assert "Played The Frog Prince" in item
    assert item.index("<strong>Story playing</strong>") < item.index("Played The Frog Prince")


def test_dashboard_upload_records_the_audit_log() -> None:
    from fastapi.testclient import TestClient

    from romini.features.audit.memory import MemoryAuditLog

    log = MemoryAuditLog()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), catalog=FakeCatalog(), audit=log))
    client.post("/tracks", files={"file": ("frog.mp3", b"id3", "audio/mpeg")})

    html = client.get("/settings").text

    assert "Stored frog.mp3" in html
    assert log.recent()[0].headline == "Track stored"
    assert log.recent()[0].summary == "Stored frog.mp3"


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
    assert "Register on" in html
    assert "Named 04aabbccddeeff Frog" in html
    assert "Saved story The station" in html
    assert "Saved studio keys" in html
    assert "gem-secret" not in html
    assert "sk_el-secret" not in html
    assert [(entry.headline, entry.summary) for entry in log.recent()] == [
        ("Studio keys saved", "Saved studio keys"),
        ("Story saved", "Saved story The station"),
        ("Figure named", "Named 04aabbccddeeff Frog"),
        ("Register on", "Register on"),
        ("Figure placed", "Placed 04aabbccddeeff"),
        ("Volume changed", "Volume set to 11"),
        ("Play mode changed", "Play mode set to tap"),
        ("Story assigned", "Assigned The Frog Prince to 04aabbccddeeff"),
    ]


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
    upload = html.index("Drag audio files directly onto this panel")
    assign = html.index("<h2>Assign a figure</h2>")
    library = html.index('<h2 class="catalog-title">Library</h2>')
    assert board < upload < library < assign
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

    scan = html.index('aria-label="Quick reader sensor"')
    figures = html.index("Figurine &amp; Tag Library")
    assert scan < figures
    assert "<h2>Present a figure</h2>" not in html
    assert "<h2>Register figures</h2>" not in html
    assert 'action="/tracks"' not in html
    assert 'action="/assign"' not in html
    assert "<h2>Library</h2>" not in html


def test_dashboard_figure_library_uses_tag_cards(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "The Gruffalo"\n'
        '  - uid: "0455a109"\n'
        '    name: "Blue Disc"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog.mp3"\n'
        '    title: "Deep Dark Wood"\n'
    )
    player = FakePlayer()
    player.play("stories/frog.mp3", position_sec=12, uid="04aabbccddeeff")
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
                player=player,
            )
        )
        .get("/figures")
        .text
    )
    library = html.split("Figurine &amp; Tag Library", 1)[1].split('class="activity-stream"', 1)[0]
    gruffalo = library.split('data-bound="yes"', 1)[1].split("</li>", 1)[0]
    unbound = library.split('data-bound="no"', 1)[1].split("</li>", 1)[0]

    assert "Search figures, stories, tags" in library
    assert "All (2)" in library
    assert "Unmapped (1)" in library
    assert "Add New Figure" not in library
    assert "04:AA:BB:CC:DD:EE:FF" in gruffalo
    assert "Deep Dark Wood" in gruffalo
    assert "Currently on Deck" in gruffalo
    assert "Configure Tag" in gruffalo
    assert 'href="/library?uid=04aabbccddeeff"' in gruffalo
    assert "Needs Audio" in unbound
    assert 'class="figure-mark figure-blank"' in unbound
    assert 'class="blank-disc"' in unbound
    assert "04:55:A1:09" in unbound
    assert "No tracks linked" in unbound
    assert "Assign Audio" in unbound
    assert 'href="/library?uid=0455a109"' in unbound


def test_dashboard_figure_can_take_a_picture(tmp_path: Path) -> None:
    import yaml
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tags:\n  - uid: "04aabbccddeeff"\n    name: "Frog"\ntracks: []\n')
    covers = tmp_path / "covers"
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            covers=covers,
            assign_catalog=PathCatalog(catalog_path),
        )
    )
    page = client.get("/figures").text

    assert 'action="/figures/cover"' in page
    assert 'aria-label="Upload picture"' in page

    stored = client.post(
        "/figures/cover",
        data={"uid": "04aabbccddeeff"},
        files={"image": ("photo.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert stored.status_code == 303
    assert stored.headers["location"].startswith("/figures")
    assert (covers / "figures" / "04aabbccddeeff" / "cover.png").read_bytes() == PNG
    image = yaml.safe_load(catalog_path.read_text())["tags"][0]["image"]
    assert image == {"file": "cover.png", "size": len(PNG), "media_type": "image/png"}
    shown = client.get("/figures").text
    assert 'src="/figures/cover/04aabbccddeeff"' in shown
    served = client.get("/figures/cover/04aabbccddeeff")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.content == PNG


def test_dashboard_figures_panels_control_playback_and_register(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import DiskStorage, PathCatalog
    from romini.fakes import FakePlayer

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog.mp3").write_bytes(b"id3")
    (library / "stories" / "bear.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "The Gruffalo"\n'
        '  - uid: "04bbccddeeff00"\n'
        '    name: "Bear"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog.mp3"\n'
        '    title: "Deep Dark Wood"\n'
        '  - uid: "04bbccddeeff00"\n'
        '    path: "stories/bear.mp3"\n'
        '    title: "Bear"\n'
    )
    player = FakePlayer()
    player.play(str(library / "stories" / "frog.mp3"), position_sec=12, uid="04aabbccddeeff")

    @dataclass
    class Register:
        assign_mode: bool = False

    client = TestClient(
        create_dashboard(
            storage=DiskStorage(library),
            assign_catalog=PathCatalog(catalog_path),
            player=player,
            mixer=FakeMixer(level=65),
            register=Register(),
        )
    )
    html = client.get("/figures").text
    deck = html.split('aria-label="Live physical deck"', 1)[1].split("</section>", 1)[0]
    scan = html.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]

    assert "Live Physical Deck" in deck
    assert "The Gruffalo" in deck
    assert "Deep Dark Wood" in deck
    assert 'action="/play"' in deck
    assert 'action="/play/previous"' in deck
    assert 'action="/play/next"' in deck
    assert 'action="/play/restart"' in deck
    assert 'name="return" value="/figures"' in deck
    assert 'action="/volume"' in deck
    assert 'name="level"' in deck
    assert 'href="/library?uid=04aabbccddeeff"' in deck
    assert "Edit Mapping" in deck
    assert "Scan &amp; Map Tag" in scan
    assert "Register Detected Token" in scan
    assert 'name="register" value="on"' in scan

    paused = client.post("/play", data={"return": "/figures"}, follow_redirects=False)
    assert paused.status_code == 303
    assert paused.headers["location"] == "/figures?notice=paused"

    nxt = client.post("/play/next", data={"return": "/figures"}, follow_redirects=False)
    assert nxt.status_code == 303
    assert nxt.headers["location"].startswith("/figures?notice=")
    assert player.playing_uid() == "04bbccddeeff00"


def test_dashboard_figures_volume_stays_on_the_figures_page() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=65))).post(
        "/volume", data={"level": "40", "return": "/figures"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=volume"


def test_dashboard_figures_studio_counts_mapped_figures(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Banana"\n'
        '  - uid: "04bbccddeeff00"\n'
        '    name: "Bear"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/romy.mp3"\n'
        '    title: "Romy"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=6 * 1024 * 1024, total_bytes=10 * 1024 * 1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/figures")
        .text
    )
    studio = html.split('class="studio"', 1)[1]
    cards = studio.split('class="summary-cards"', 1)[1].split('class="studio-main"', 1)[0]
    mapped = cards.split("Mapped Figurines", 1)[1].split("Audio Track Library", 1)[0]
    library = cards.split("Audio Track Library", 1)[1]

    assert ">1<" in mapped
    assert "Active" in mapped
    assert "1 tag requires audio link" in mapped
    assert 'style="width: 50%"' in mapped
    assert ">1<" in library
    assert "Tracks" in library
    assert "4.0 MB of 10.0 MB MicroSD" in library
    assert 'style="width: 40%"' in library


def test_dashboard_figures_shows_todays_listening_time() -> None:
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    from romini.features.listening.log import MemoryPlayLog

    now = datetime.now().astimezone()
    log = MemoryPlayLog()
    log.begin(now - timedelta(hours=1, minutes=35))
    log.end(now)

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), listening=log)).get("/figures").text
    card = html.split("Today&#39;s Session", 1)[-1]
    if "Today&#39;s Session" not in html:
        card = html.split("Today's Session", 1)[1]
    card = card.split("</li>", 1)[0]

    assert "1h 35m" in card
    assert "bedtime" not in card.lower()


def test_dashboard_figure_card_shows_the_story_bound_to_it(tmp_path: Path) -> None:
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
        .get("/figures")
        .text
    )
    card = html.split('class="figure"', 1)[1].split("</li>", 1)[0]

    assert "Romy and the banana" in card


def test_dashboard_figure_card_shows_the_length_of_its_story(tmp_path: Path) -> None:
    import io
    import wave

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Banana"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/romy.wav"\n'
        '    title: "Romy"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, files={"stories/romy.wav": buffer.getvalue()}),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/figures")
        .text
    )
    card = html.split('class="figure"', 1)[1].split("</li>", 1)[0]

    assert "Romy" in card
    assert "0:01" in card
    assert "15.7 KB" in card


def test_dashboard_figure_card_says_when_no_story_is_linked(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tags:\n  - uid: "04aabbccddeeff"\n    name: "Banana"\ntracks: []\n')
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
    card = html.split('class="figure"', 1)[1].split("</li>", 1)[0]

    assert "No story linked" in card


def test_dashboard_figure_card_leads_with_the_figure_name(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tags:\n  - uid: "04aabbccddeeff"\n    name: "Banana"\ntracks: []\n')
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
    card = html.split('class="figure"', 1)[1].split("</li>", 1)[0]

    assert card.index("<h3>Banana</h3>") < card.index('class="uid"')


def test_dashboard_chrome_sits_in_the_same_column_as_the_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    shell = html.index('class="shell"')
    header = html.index("<header")
    main = html.index("<main")
    end_main = html.index("</main>")
    end_shell = html.index("</div>", end_main)

    assert shell < header < main < end_main < end_shell
    assert "max-width: 77.5rem" in html
    assert ">RoMini<" in html.replace("<span>", "").replace("</span>", "")
    assert 'href="/figures"' in html
    assert 'class="page-title"' in html
    assert ">Live Player<" in html
    assert 'href="/library"' in html
    assert 'href="/settings"' in html
    assert 'href="/write"' not in html
    assert "Toys" not in html


def test_dashboard_home_jump_list_includes_characters() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/characters").text

    assert 'href="/characters"' in html
    assert ">Characters<" in html


def test_dashboard_home_shows_the_box_picture() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'src="/mark.svg"' in html
    assert 'class="page-title"' in html


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
    assert ">Figure<" in html
    assert "Frog" in html
    assert ">Time<" in html
    assert "22:33" in html


def test_dashboard_live_player_splits_the_plate_from_the_story(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 125.0

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
    studio = html.split('class="studio"', 1)[1].split("</script>", 1)[0]

    assert studio.index("On the plate") < studio.index('class="deck-title"')
    assert ">Frog<" in studio
    assert 'querySelector(".studio")' in html


def test_dashboard_live_player_plate_shows_the_mark() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    plate = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]

    assert 'class="plate-mark"' in plate
    assert 'src="/mark.svg"' in plate


def test_dashboard_live_player_docks_the_figure_inside_the_plate(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 125.0

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
    plate = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]
    head, ring = plate.split('class="dock-ring"', 1)
    face = ring.split("dock-facts", 1)[0]

    assert "UID 04aabbccddeeff" in head
    assert ">Frog<" in face
    assert "The Frog Prince" in face
    assert "Contact verified" in face
    assert 'class="dock-check"' in face
    assert "Hand-carved" not in plate
    assert "100%" not in plate


def test_dashboard_figures_plate_shows_the_mark() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    plate = html.split('aria-label="Live physical deck"', 1)[1].split("</section>", 1)[0]

    assert 'class="plate-mark"' in plate
    assert 'src="/mark.svg"' in plate


def test_dashboard_live_player_deck_leads_with_the_story(tmp_path: Path) -> None:
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

    assert '<h2 class="deck-title">The Frog Prince</h2>' in html
    assert ">Now playing<" in html
    assert ">Story<" in html


def test_dashboard_live_player_names_the_docked_figure_and_its_place(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 125.0

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

    assert ">Figure<" in html
    assert ">Frog<" in html
    assert ">Place<" in html
    assert ">2:05<" in html


def test_dashboard_live_player_shows_how_far_through_the_story(tmp_path: Path) -> None:
    import io
    import wave
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/romy.wav"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

        def position_sec(self) -> float:
            return 0.5

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/romy.wav"\n'
        '    title: "Romy"\n'
        "tags:\n"
        "  - uid: 04aabbccddeeff\n"
        "    name: Romy\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, files={"stories/romy.wav": buffer.getvalue()}),
                assign_catalog=PathCatalog(catalog_path),
                player=Playing(),
            )
        )
        .get("/")
        .text
    )
    deck = html.split('aria-label="Now playing"', 1)[1].split("</section>", 1)[0]

    assert 'class="scrub"' in deck
    assert 'style="width: 50%"' in deck
    assert deck.index('class="scrub"') < deck.index(">0:01<")


def test_dashboard_live_player_seeks_when_the_scrubber_moves(tmp_path: Path) -> None:
    import io
    import wave

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/romy.wav"\n    title: "Romy"\n')
    player = FakePlayer()
    player.play("stories/romy.wav", position_sec=0.0, uid="04aabbccddeeff")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024, files={"stories/romy.wav": buffer.getvalue()}),
            assign_catalog=PathCatalog(catalog_path),
            player=player,
        )
    )
    deck = client.get("/").text.split('aria-label="Now playing"', 1)[1]

    assert 'action="/play/seek"' in deck
    assert 'name="progress"' in deck
    response = client.post("/play/seek", data={"progress": "50"}, follow_redirects=False)

    assert response.status_code == 303
    assert player.plays[-1] == ("stories/romy.wav", 0.5)


def test_dashboard_scrubber_seeks_without_submitting_over_play(tmp_path: Path) -> None:
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

        def position_sec(self) -> float:
            return 1.0

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "stories/frog-prince.mp3"\n    title: "The Frog Prince"\n'
    )
    page = (
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
    deck = page.split('aria-label="Now playing"', 1)[1].split("</section>", 1)[0]
    transport = deck.split('class="transport"', 1)[1]

    assert 'action="/play"' in transport
    assert "requestSubmit" not in deck
    assert 'fetch("/play/seek"' in page


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


def test_dashboard_play_and_pause_records_todays_listening() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer
    from romini.features.listening.log import MemoryPlayLog

    player = FakePlayer()
    player.select("04aabbccddeeff", "stories/frog-prince.mp3")
    log = MemoryPlayLog()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player, listening=log))

    client.post("/play", follow_redirects=False)
    client.post("/play", follow_redirects=False)

    intervals = log.intervals()
    assert len(intervals) == 1
    assert intervals[0].ended_at is not None
    assert intervals[0].ended_at >= intervals[0].started_at


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


def test_dashboard_live_player_restarts_the_story_from_the_laptop() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    player = FakePlayer()
    player.play("stories/frog-prince.mp3", position_sec=40.0, uid="04aabbccddeeff")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player))
    html = client.get("/").text

    assert 'action="/play/restart"' in html
    assert ">Restart<" in html
    response = client.post("/play/restart", follow_redirects=False)

    assert response.status_code == 303
    assert player.is_playing() is True
    assert player.plays[-1] == ("stories/frog-prince.mp3", 0.0)


def test_dashboard_live_player_follows_the_plate_without_reloading(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

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
    player = FakePlayer()
    player.play("stories/frog-prince.mp3", position_sec=40.0, uid="04aabbccddeeff")
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            assign_catalog=PathCatalog(catalog_path),
            player=player,
        )
    )
    page = client.get("/").text

    assert 'fetch("/now-playing")' in page
    assert "location.reload" not in page
    assert ">Frog<" in client.get("/now-playing").text
    player.pause()
    lifted = client.get("/now-playing").text
    assert ">Paused<" in lifted
    assert "location.reload" not in lifted


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


def test_dashboard_quiet_deck_play_submits_when_a_player_is_connected() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=FakePlayer())).get("/").text
    quiet = html.split('class="deck card quiet"', 1)[1].split("</section>", 1)[0]

    assert 'action="/play"' in quiet
    assert 'class="play-main" disabled' not in quiet
    assert "cursor: wait" not in html


def test_dashboard_deck_play_draws_a_play_mark() -> None:
    from datetime import datetime

    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    quiet = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=FakePlayer()))
        .get("/")
        .text.split('class="deck card quiet"', 1)[1]
        .split("</section>", 1)[0]
    )

    assert 'class="play-glyph"' in quiet
    assert "M8 5v14l11-7z" in quiet

    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

    playing = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=Playing()))
        .get("/")
        .text.split('aria-label="Now playing"', 1)[1]
        .split("</section>", 1)[0]
    )

    assert 'class="play-glyph"' in playing
    assert "M6 5h4v14H6z" in playing


def test_dashboard_quiet_deck_draws_seek_marks() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    quiet = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=FakePlayer()))
        .get("/")
        .text.split('class="deck card quiet"', 1)[1]
        .split("</section>", 1)[0]
    )

    assert quiet.count('class="seek-glyph"') == 3


def test_dashboard_write_page_lets_you_pick_a_named_voice(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    client.post("/stories", data={"story_title": "The little station", "script": "Hello."})
    html = client.get("/stories").text

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


def test_dashboard_library_audition_bar_stays_in_the_page_column() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )
    rule = html.split(".audition-bar {", 1)[1].split("}", 1)[0]

    assert "position: fixed" not in rule
    assert "translateX" not in rule
    assert 'class="audition-bar"' in html


def test_dashboard_library_audition_controls_share_one_row() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )
    bar = html.split('class="audition-bar"', 1)[1].split("</section>", 1)[0]
    copy = bar.split('class="audition-copy"', 1)[1].split("</div>", 1)[0]
    rule = html.split(".audition-bar {", 1)[1].split("}", 1)[0]

    assert 'id="preview"' not in copy
    assert 'id="preview"' in bar
    assert 'id="player"' in bar
    assert "flex-wrap: nowrap" in rule


def test_dashboard_library_lets_you_listen_to_a_track() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )

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


def test_dashboard_story_page_lets_you_listen_to_the_spoken_file(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    pack = tmp_path / "the-little-station"
    pack.mkdir()
    (pack / "story.yaml").write_text("title: The little station\nscript: hello\n")
    (pack / "spoken.mp3").write_bytes(b"id3")
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
        .get("/stories/the-little-station")
        .text
    )

    assert "<audio" in html
    assert "controls" in html
    assert 'id="player"' in html
    assert 'value="/library/file/spoken.mp3"' in html
    assert "player.src = select.value" in html
    assert 'aria-label="Preview"' in html


def test_dashboard_serves_the_spoken_story_for_preview(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    pack = tmp_path / "the-little-station"
    pack.mkdir()
    (pack / "story.yaml").write_text("title: The little station\nscript: hello\n")
    (pack / "spoken.mp3").write_bytes(b"id3")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path)).get(
        "/stories/the-little-station/spoken"
    )

    assert response.status_code == 200
    assert response.content == b"id3"
    assert response.headers["content-type"].startswith("audio/")


def test_dashboard_speak_warns_that_the_existing_track_will_be_replaced(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    pack = tmp_path / "the-little-station"
    pack.mkdir()
    (pack / "story.yaml").write_text("title: The little station\nscript: hello\n")
    (pack / "spoken.mp3").write_bytes(b"id3")
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
        .get("/stories/the-little-station")
        .text
    )
    speak = html.split('action="/stories/speak"', 1)[1].split("</form>", 1)[0]

    assert "Speaking again replaces spoken.mp3." in speak


def test_dashboard_spoken_preview_answers_a_range_request(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    pack = tmp_path / "super-story"
    pack.mkdir()
    (pack / "story.yaml").write_text("title: Super story\nscript: hello\n")
    (pack / "super-story.mp3").write_bytes(b"ID3audio-bytes")
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path)).get(
        "/stories/super-story/spoken",
        headers={"Range": "bytes=0-2"},
    )

    assert response.status_code == 206
    assert response.content == b"ID3"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-range"] == "bytes 0-2/14"


def test_dashboard_story_listen_loads_the_library_preview_url(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    pack = tmp_path / "the-little-station"
    pack.mkdir()
    (pack / "story.yaml").write_text("title: The little station\nscript: hello\n")
    (pack / "spoken.mp3").write_bytes(b"id3")
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024, files={"spoken.mp3": b"id3"}),
                stories=tmp_path,
            )
        )
        .get("/stories/the-little-station")
        .text
    )
    listen = html.split('<label for="preview">Preview</label>', 1)[1]

    assert 'id="player"' in listen
    assert "player.src = select.value" in listen
    assert 'value="/library/file/spoken.mp3"' in listen
    assert 'src="/stories/' not in listen


def test_dashboard_library_selects_the_figure_from_the_queue(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Banana"\n'
        '  - uid: "04ffeeddccbbaa"\n'
        '    name: "Frog"\n'
        "tracks: []\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library?uid=04ffeeddccbbaa")
        .text
    )
    option = html.split('value="04ffeeddccbbaa"', 1)[1].split("</option>", 1)[0]

    assert "selected" in option
    assert 'name="bind"' in html
    assert "Prompt physical tag binding immediately after transfer" in html


def test_dashboard_upload_can_ask_for_a_figure_link_next() -> None:
    from fastapi.testclient import TestClient

    storage = FakeStorage(free_bytes=1024)
    response = TestClient(create_dashboard(storage=storage, catalog=FakeCatalog())).post(
        "/tracks",
        files={"file": ("frog.mp3", b"id3", "audio/mpeg")},
        data={"bind": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=uploaded&bind=1"
    html = TestClient(create_dashboard(storage=storage)).get("/library?bind=1").text
    assert "Link the new track to a figure." in html


def test_dashboard_emergency_mute_sets_the_mixer_to_zero() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=40)
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer))
    home = client.get("/").text

    assert 'action="/mute"' in home
    assert 'action="/volume"' not in home
    response = client.post("/mute", follow_redirects=False)

    assert response.status_code == 303
    assert mixer.level == 0


def test_dashboard_shows_the_connected_wifi_name(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from romini.composition.dashboard import shared

    def run(args: list[str], **_kwargs: object) -> object:
        assert args == ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"]

        class Completed:
            stdout = "no:Neighbour\nyes:House\n"

        return Completed()

    monkeypatch.setattr(shared, "subprocess", SimpleNamespace(run=run), raising=False)
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    network = html.split("<h2>Network</h2>", 1)[1].split("</section>", 1)[0]
    pills = html.split('class="status-pills"', 1)[1].split("</ul>", 1)[0]

    assert ">House<" in network
    assert "Wi-Fi House" in pills
    assert "sudo nmtui" in network


def test_dashboard_hardware_shows_live_host_facts_without_inventing_wifi() -> None:
    import socket

    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "<h2>Host</h2>" in html
    assert "<h2>Network</h2>" in html
    assert socket.gethostname() in html
    assert ">Wi-Fi<" in html
    assert "Not reported" in html
    assert "sudo nmtui" in html
    assert "software ceiling" not in html.lower()


def test_dashboard_power_controls_stay_off_until_a_box_is_wired() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "Safe power down" in html
    assert 'action="/system/power"' not in html
    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).post(
        "/system/power",
        data={"action": "poweroff"},
    )
    assert response.status_code == 404


def test_dashboard_safe_power_down_calls_the_box_halt() -> None:
    from fastapi.testclient import TestClient

    class Power:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def restart(self) -> None:
            self.actions.append("restart")

        def reboot(self) -> None:
            self.actions.append("reboot")

        def poweroff(self) -> None:
            self.actions.append("poweroff")

    power = Power()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), power=power))
    html = client.get("/settings").text

    assert 'action="/system/power"' in html
    assert "Restart daemon" in html
    response = client.post("/system/power", data={"action": "poweroff"}, follow_redirects=False)

    assert response.status_code == 303
    assert power.actions == ["poweroff"]
    assert "Power request sent" in client.get("/settings?notice=power").text


PNG = b"\x89PNG\r\n\x1a\n" + b"IHDR" + b"\x00" * 8


def test_dashboard_story_cover_is_stored_on_the_box_and_listed(tmp_path: Path) -> None:
    import yaml
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "station.mp3"\n    title: "The little station"\n'
    )
    covers = tmp_path / "covers"
    storage = FakeStorage(free_bytes=1024)
    storage.put("station.mp3", b"id3")
    client = TestClient(create_dashboard(storage=storage, covers=covers, assign_catalog=PathCatalog(catalog_path)))

    stored = client.post(
        "/library/cover",
        data={"path": "station.mp3"},
        files={"image": ("photo.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert stored.status_code == 303
    assert stored.headers["location"].startswith("/library")
    assert (covers / "station.mp3" / "cover.png").read_bytes() == PNG
    assert "cover.png" not in storage.files
    track = yaml.safe_load(catalog_path.read_text())["tracks"][0]["image"]
    assert track == {"file": "cover.png", "size": len(PNG), "media_type": "image/png"}
    assert "story" not in track
    library = client.get("/library").text
    assert 'src="/library/cover/station.mp3"' in library
    assert 'action="/library/cover"' in library
    served = client.get("/library/cover/station.mp3")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.content == PNG


def test_dashboard_uploaded_track_can_take_a_cover_without_a_story(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")
    covers = tmp_path / "covers"
    storage = FakeStorage(free_bytes=1024)
    storage.put("bedtime.mp3", b"id3")
    client = TestClient(create_dashboard(storage=storage, covers=covers, assign_catalog=PathCatalog(catalog_path)))
    page = client.get("/library").text

    assert 'action="/library/cover"' in page
    assert 'value="bedtime.mp3"' in page

    stored = client.post(
        "/library/cover",
        data={"path": "bedtime.mp3"},
        files={"image": ("photo.png", PNG, "image/png")},
        follow_redirects=False,
    )

    assert stored.status_code == 303
    assert (covers / "bedtime.mp3" / "cover.png").read_bytes() == PNG
    assert "cover.png" not in storage.files


def test_dashboard_story_list_and_player_use_the_logo_when_no_cover_is_set(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "station.mp3"\n    title: "The little station"\n'
    )
    stories = tmp_path / "stories"
    client = TestClient(
        create_dashboard(
            storage=FakeStorage(free_bytes=1024),
            stories=stories,
            assign_catalog=PathCatalog(catalog_path),
        )
    )
    client.post("/stories", data={"story_title": "The little station"})
    page = client.get("/stories").text
    library = client.get("/library").text

    assert 'action="/stories/image"' not in page
    assert 'src="/logo.svg"' in library.split("<caption>Library</caption>", 1)[1]
    player = FakePlayer()
    player.play("station.mp3", position_sec=1.0, uid="04aabbccddeeff")
    playing = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                stories=stories,
                assign_catalog=PathCatalog(catalog_path),
                player=player,
            )
        )
        .get("/now-playing")
        .text
    )
    now = playing.split('aria-label="Now playing"', 1)[1]
    assert '<img class="cover" src="/logo.svg" alt="">' in now


def test_dashboard_player_shows_the_story_cover(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    cover = tmp_path / "covers" / "station.mp3"
    cover.mkdir(parents=True)
    (cover / "cover.png").write_bytes(PNG)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        'tracks:\n  - uid: "04aabbccddeeff"\n    path: "station.mp3"\n    title: "The little station"\n'
    )
    storage = FakeStorage(free_bytes=1024)
    storage.put("station.mp3", b"id3")
    player = FakePlayer()
    player.play("station.mp3", position_sec=1.0, uid="04aabbccddeeff")
    html = (
        TestClient(
            create_dashboard(
                storage=storage,
                covers=tmp_path / "covers",
                assign_catalog=PathCatalog(catalog_path),
                player=player,
            )
        )
        .get("/now-playing")
        .text
    )

    now = html.split('aria-label="Now playing"', 1)[1]
    assert '<img class="cover" src="/library/cover/station.mp3" alt="">' in now


def test_dashboard_rejects_a_cover_that_is_not_an_image(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    covers = tmp_path / "covers"
    storage = FakeStorage(free_bytes=1024)
    storage.put("station.mp3", b"id3")
    client = TestClient(create_dashboard(storage=storage, covers=covers))
    rejected = client.post(
        "/library/cover",
        data={"path": "station.mp3"},
        files={"image": ("notes.html", b"<html></html>", "text/html")},
        follow_redirects=False,
    )

    assert rejected.status_code == 303
    assert "notice=image-needed" in rejected.headers["location"]
    assert not (covers / "station.mp3").exists()


def test_dashboard_saving_a_story_keeps_its_cover(tmp_path: Path) -> None:
    import yaml
    from fastapi.testclient import TestClient

    stories = tmp_path / "stories"
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=stories))
    client.post("/stories", data={"story_title": "The little station", "outline": "a ride"})
    client.post("/stories", data={"story_title": "The little station", "outline": "a longer ride"})

    notes = yaml.safe_load((stories / "the-little-station" / "story.yaml").read_text())
    assert "image" not in notes
    assert notes["outline"] == "a longer ride"
    assert 'action="/stories/image"' not in client.get("/stories").text


def test_dashboard_assign_writes_the_cover_onto_the_track(tmp_path: Path) -> None:
    import yaml
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    cover = tmp_path / "covers" / "station.mp3"
    cover.mkdir(parents=True)
    (cover / "cover.png").write_bytes(PNG)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks: []\n")
    storage = FakeStorage(free_bytes=1024)
    storage.put("station.mp3", b"id3")
    client = TestClient(
        create_dashboard(
            storage=storage,
            covers=tmp_path / "covers",
            assign_catalog=PathCatalog(catalog_path),
        )
    )
    response = client.post(
        "/assign",
        data={"uid": "04aabbccddeeff", "path": "station.mp3", "title": "The little station"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    image = yaml.safe_load(catalog_path.read_text())["tracks"][0]["image"]
    assert image["file"] == "cover.png"
    assert image["media_type"] == "image/png"
    assert "story" not in image


def test_dashboard_home_keeps_the_volume_readout_and_eject() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=40, ceiling=75)))
        .get("/")
        .text
    )

    assert "Volume cap" in html
    assert "40 of 75" in html
    assert "Stop &amp; Eject" in html
    assert "Raspberry Pi Safety" not in html
    assert "Sleep in 30m" not in html
    assert 'action="/safety/beep"' not in html
    assert "dB" not in html


def test_dashboard_stop_and_eject_stops_playback() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    player = FakePlayer()
    player.play("story.mp3", position_sec=12.0, uid="04aabbccddeeff")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player))

    assert 'action="/safety/eject"' in client.get("/").text
    response = client.post("/safety/eject", follow_redirects=False)

    assert response.status_code == 303
    assert player.stops == 1
    assert player.is_playing() is False


def test_dashboard_safety_card_reboots_and_shows_the_address() -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard.shared import read_host_facts

    class Power:
        def __init__(self) -> None:
            self.actions: list[str] = []

        def restart(self) -> None:
            self.actions.append("restart")

        def reboot(self) -> None:
            self.actions.append("reboot")

        def poweroff(self) -> None:
            self.actions.append("poweroff")

    power = Power()
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), power=power))
    home = client.get("/").text
    hardware = client.get("/settings").text

    assert "Clean Pi OS Reboot" not in home
    assert 'name="action" value="reboot"' not in home
    assert 'name="action" value="reboot"' in hardware
    assert read_host_facts()["address"] in hardware
    response = client.post("/system/power", data={"action": "reboot", "return": "/"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/?")
    assert power.actions == ["reboot"]


def test_dashboard_nfc_beep_stays_on_until_the_parent_turns_it_off(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings))
    card = client.get("/settings").text.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert 'action="/safety/beep"' in card
    assert 'aria-checked="true"' in card
    response = client.post("/safety/beep", data={"nfc_beep": "off"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings")
    assert settings.nfc_beep() is False
    again = client.get("/settings").text.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]
    assert 'aria-checked="false"' in again


def test_dashboard_sleep_arms_a_thirty_minute_bedtime(tmp_path: Path) -> None:
    from datetime import datetime, timedelta

    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings))
    before = datetime.now().astimezone()

    assert "Sleep in 30m" in client.get("/settings").text
    response = client.post("/safety/sleep", follow_redirects=False)
    deadline = settings.sleep_at()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings")
    assert deadline is not None
    assert timedelta(minutes=29, seconds=50) <= deadline - before <= timedelta(minutes=30, seconds=10)
    assert "Sleeping in 30m" in client.get("/settings").text


def test_dashboard_sleep_can_be_cancelled(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings))
    client.post("/safety/sleep")
    card = client.get("/settings").text.split('aria-label="Parental audio safety"', 1)[1].split("</section>", 1)[0]

    assert 'name="cancel" value="1"' in card
    response = client.post("/safety/sleep", data={"cancel": "1"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings")
    assert settings.sleep_at() is None
    assert "Sleep in 30m" in client.get("/settings").text
