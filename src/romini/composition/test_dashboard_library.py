from dataclasses import dataclass, field
from pathlib import Path

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import DiskStorage, create_dashboard
from romini.features.library.import_catalog import import_catalog
from romini.features.play_by_tag.place_figure import PlayMode

PNG = b"\x89PNG\r\n\x1a\n" + b"IHDR" + b"\x00" * 8


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


@dataclass
class FakeMixer:
    level: int
    ceiling: int = 100

    def set_level(self, level: int) -> None:
        self.level = level


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

    file_input = html.split('id="file"', 1)[1].split(">", 1)[0]
    assert "multiple" in file_input
    assert 'accept="audio/*"' in file_input
    assert "webkitdirectory" not in html


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


def test_dashboard_assign_form_marks_required_fields(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text("tracks:\n  - path: stories/pond.mp3\n    title: The pond\n")
    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), assign_catalog=PathCatalog(catalog_path)))
        .get("/library")
        .text
    )

    assert "<legend>Figure</legend>" in html
    assert 'name="title"' in html
    assert 'type="text" required' in html
    assert 'name="path"' in html
    assign = html.split('action="/assign"', 1)[1]
    assert "required" in assign.split('name="path"', 1)[1].split(">", 1)[0]


def test_dashboard_library_page_matches_the_audio_library_layout() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert "MicroSD Capacity" in html
    assert "Total Audio Assets" in html
    assert "NFC Pairing" in html
    assert "DAC Configuration" in html
    assert "Drag audio files directly onto this panel" in html
    assert "Active Sync Queue" in html
    assert "Figure" in html
    assert "Choose audio files" in html
    assert "Browse Laptop Disk" not in html
    assert 'id="folder"' not in html
    assert 'id="sync-retry"' in html
    assert 'class="card deck' not in html
    assert 'class="card scan-dock"' not in html


def test_dashboard_library_tracks_use_nordic_cards_and_an_empty_state() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="quota-cards"' in html
    assert html.count('class="card') >= 2
    assert "No stories yet. Upload a track, then assign a figure." in html
    assert 'for="file"' in html
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


def test_dashboard_sync_queue_reports_the_file_being_transferred() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    queue = html.split('aria-label="Active sync queue"', 1)[1].split("</section>", 1)[0]
    script = html.split('id="upload-well"', 1)[1].split("</section>", 1)[0]

    assert 'id="sync-status"' in queue
    assert 'id="sync-meter"' in queue
    assert "XMLHttpRequest" in script
    assert script.index('append("file"') < script.index(".send(")
    assert 'upload.addEventListener("progress"' in script
    assert script.index('meter.setAttribute("aria-valuenow"') < script.index("next.click()")
    assert "form.submit()" not in script


def test_dashboard_library_upload_well_takes_a_dropped_audio_file() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    well = html.split('id="upload-well"', 1)[1].split("</section>", 1)[0]

    assert well.index("Drag audio files directly onto this panel") < well.index('id="file"')
    assert 'addEventListener("drop"' in well
    drop = well.split('addEventListener("drop"', 1)[1]
    assert drop.index("enqueue(event.dataTransfer.files)") < drop.index("function enqueue")
    assert well.count('addEventListener("change"') == 1


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

    assert 'name="path" value="frog.mp3"' in html
    assert 'name="path" value="stories/frog-prince.mp3"' in html


def test_dashboard_assign_path_empty_when_library_has_no_files() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert "No stories yet. Upload a track, then assign a figure." in html


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
    stop = playing.split('aria-label="Stop"', 1)[1].split("</button>", 1)[0]
    assert 'd="M6 6h12v12H6z"' in stop
    assert "M9 7.5v9l8-4.5z" not in stop
    assert "Active Preview" in playing
    assert 'class="credit-name"' in playing
    assert "Julia Donaldson" in playing
    assert 'class="chip linked"' in playing
    assert "The Gruffalo Figurine" in playing
    assert 'class="row-actions"' in playing
    assert 'aria-label="Change picture"' in playing
    assert ">Edit<" in playing
    assert 'data-path="stories/gruffalo.mp3"' in playing
    assert 'aria-label="Upload cover"' not in playing
    assert "unlinked" in catalog.split(">The Very Hungry Caterpillar<", 1)[0].rsplit("<tr", 1)[1]
    assert 'class="chip missing"' in waiting
    assert "No figure linked" in waiting
    assert 'class="link-tag"' in waiting
    assert "Link figure" in waiting


def test_dashboard_library_file_spec_column_keeps_the_size_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    spec = html.split(".library-catalog td:nth-child(5)", 1)[1].split("}", 1)[0]
    title = html.split(".library-catalog td:has(input)", 1)[1].split("}", 1)[0]

    assert "white-space: nowrap" in spec
    assert "width: 100%" not in title


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


def test_dashboard_place_starts_the_mapped_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    @dataclass
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


def test_dashboard_library_page_puts_upload_and_assign_above_the_catalog() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'href="/library"' in html
    assert ">Library<" in html
    assert 'aria-current="page"' in html
    board = html.index('class="board"')
    upload = html.index("Drag audio files directly onto this panel")
    library = html.index('<h2 class="catalog-title">Library</h2>')
    assert board < upload < library
    assert 'action="/tracks"' in html
    assert "<h2>Assign a figure</h2>" not in html


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


def test_track_cover_stores_and_finds_a_png(tmp_path: Path) -> None:
    from romini.composition.dashboard.covers import locate_track_cover, save_track_cover

    saved = save_track_cover(tmp_path, "stories/frog.mp3", b"\x89PNG\r\n\x1a\n")
    found = locate_track_cover(tmp_path, "stories/frog.mp3")

    assert saved is not None
    assert saved["file"] == "cover.png"
    assert found is not None
    assert found[0].name == "cover.png"


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

    assert head.index("<th>Story Title</th>") < head.index("<th>Figure</th>")
    assert row.index('class="track-title"') < row.index('class="chip linked"')
    assert ">Romy and the banana<" in row
    assert ">Banana<" in row


def test_dashboard_library_keeps_display_mode_and_shows_the_filtered_count(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tracks:\n"
        "  - path: stories/pond.mp3\n"
        "    title: The pond\n"
        "  - path: stories/hill.mp3\n"
        "    title: The hill\n"
        "    uid: '04aabbccddeeff'\n"
        "tags:\n"
        "  - uid: '04aabbccddeeff'\n"
        "    name: Frog\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library?view=grid&q=pond")
        .text
    )

    assert 'id="view-grid"' in html
    assert 'href="/library?view=grid' in html
    assert 'aria-pressed="true"' in html.split('id="view-grid"', 1)[1].split(">", 1)[0]
    assert "Showing 1 of 2" in html
    assert ">The hill<" not in html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def test_dashboard_display_mode_marks_the_active_view_on_white() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    rule = html.split('.view-switch .chip-btn[aria-pressed="true"] {', 1)[1].split("}", 1)[0]

    assert "background: #fff" in rule
    assert "color: #2b2825" in rule


def test_dashboard_library_assigns_a_figure_from_the_track_row(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Frog"\n'
        "tracks:\n"
        '  - path: "stories/pond.mp3"\n'
        '    title: "The pond"\n'
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
    row = table.split(">The pond<", 1)[1].split("</tr>", 1)[0]
    below = html.split("</table>", 1)[1]

    assert 'action="/assign"' in row
    assert 'name="path" value="stories/pond.mp3"' in row
    assert 'action="/assign"' not in below


def test_dashboard_assign_popover_shows_the_figure_tiles() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    rule = html.split(".library-catalog td label.figure-tile {", 1)[1].split("}", 1)[0]

    assert "width: auto" in rule
    assert "height: auto" in rule
    assert "overflow: visible" in rule
    assert "clip: auto" in rule


def test_dashboard_assign_row_opens_wide_enough_to_name_the_figure() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    rule = html.split(".row-assign[open] form {", 1)[1].split("}", 1)[0]

    assert "width: min(24rem, 70vw)" in rule
    assert "position: absolute" in rule
