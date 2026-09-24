from dataclasses import dataclass, field
from pathlib import Path

from romini.composition.dashboard import DiskStorage, create_dashboard

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


def test_dashboard_status_and_scan_share_one_line_at_the_same_height() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    cluster = header.split('class="top-actions"', 1)[1].split("</div>", 1)[0]
    pills = html.split(".status-pills li {", 1)[1].split("}", 1)[0]
    row = html.split(".top-actions {", 1)[1].split("}", 1)[0]

    assert "status-pills" in cluster
    assert 'class="scan"' not in cluster
    assert "flex-wrap: nowrap" in row
    assert "min-height: 2.5rem" in pills
    assert "white-space: nowrap" in pills


def test_dashboard_tap_mode_copy_says_tap_starts_and_same_figure_pauses() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text

    assert "tap the figure to start" in html
    assert "same figure again to pause" in html


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
    assert "No figure linked" in row


def test_dashboard_register_mode_enters_assign_mode() -> None:
    from fastapi.testclient import TestClient

    @dataclass
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

    @dataclass
    class FakeRegister:
        assign_mode = True

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/figures").text
    )
    scan = html.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]

    assert "<h2>Register figures</h2>" not in html
    assert 'name="register" value="off"' in scan
    assert "Stop registering" in scan


def test_dashboard_scan_dock_matches_reader_card_and_pulses_only_while_registering() -> None:
    from fastapi.testclient import TestClient

    class Idle:
        assign_mode = False

    class Listening:
        assign_mode = True

    idle = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=Idle())).get("/figures").text
    idle_scan = idle.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]
    assert 'class="scan-target"' in idle_scan
    assert "Reader is Listening" in idle_scan
    assert "Place a figure on the box" in idle_scan
    assert 'class="scan-live"' in idle_scan
    assert "is-registering" not in idle_scan

    listening = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=Listening())).get("/figures").text
    )
    listening_scan = listening.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]
    assert "is-registering" in listening_scan
    assert "Stop registering" in listening_scan


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

    assign = html.split("<h2>Assign a figure</h2>", 1)[1].split('<select id="path"', 1)[0]
    assert '<select id="uid"' not in assign
    assert 'class="figure-tile"' in assign
    assert 'value="04aabbccddeeff"' in assign
    assert ">Frog Prince<" in assign


def test_dashboard_assign_shows_each_figure_as_a_picture_tile(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    cover = tmp_path / "covers" / "figures" / "04aabbccddeeff"
    cover.mkdir(parents=True)
    (cover / "cover.png").write_bytes(PNG)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Frog Prince"\n'
        '  - uid: "0455a109"\n'
        '    name: "Blue Disc"\n'
        "tracks: []\n"
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                covers=tmp_path / "covers",
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/library")
        .text
    )
    assign = html.split("<h2>Assign a figure</h2>", 1)[1].split("</form>", 1)[0]

    assert 'name="uid"' in assign
    assert "<select" not in assign.split('<select id="path"', 1)[0]
    assert 'class="figure-tiles"' in assign
    frog = assign.split(">Frog Prince<", 1)[0]
    assert 'src="/figures/cover/04aabbccddeeff"' in frog
    assert 'type="radio"' in frog
    assert 'name="uid"' in frog
    assert 'value="04aabbccddeeff"' in frog
    blank = assign.split(">Blue Disc<", 1)[0].rsplit('class="figure-tile"', 1)[1]
    assert 'src="/mark.svg"' in blank


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


def test_dashboard_register_on_refreshes_home() -> None:
    from fastapi.testclient import TestClient

    @dataclass
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

    @dataclass
    class FakePad:
        def place(self, uid: str) -> None:
            return

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).get("/figures").text

    assert "<h2>Present a figure</h2>" not in html
    assert 'action="/present"' not in html
    assert 'id="present-uid"' not in html


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
    library = html.split("<h2>Figures</h2>", 1)[1].split('class="activity-stream"', 1)[0]
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
    assert 'href="/library?uid=04aabbccddeeff#assign"' in gruffalo
    assert "Needs Audio" in unbound
    assert 'class="figure-mark figure-blank"' in unbound
    assert 'class="blank-disc"' in unbound
    assert "04:55:A1:09" in unbound
    assert "No tracks linked" in unbound
    assert "Assign Audio" in unbound
    assert 'href="/library?uid=0455a109#assign"' in unbound


def test_dashboard_figure_library_switches_between_list_and_grid(tmp_path: Path) -> None:
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
    toolbar = html.split('class="figure-toolbar"', 1)[1].split('id="figure-list"', 1)[0]
    script = html.split('id="figure-list"', 1)[1].split("</script>", 1)[0]
    list_rule = html.split(".figures.is-list {", 1)[1].split("}", 1)[0]
    switch = html.split(".figure-library .view-switch {", 1)[1].split("}", 1)[0]
    pressed = html.split('.figure-library .view-switch .chip-btn[aria-pressed="true"] {', 1)[1].split("}", 1)[0]
    grid = toolbar.split('id="figure-view-grid"', 1)[1].split(">", 1)[0]
    listing = toolbar.split('id="figure-view-list"', 1)[1].split(">", 1)[0]

    assert "Display Mode" in toolbar
    assert 'aria-label="Display mode"' in toolbar
    assert 'aria-label="List view"' in listing
    assert 'aria-pressed="false"' in listing
    assert 'aria-label="Grid view"' in grid
    assert 'aria-pressed="true"' in grid
    assert 'class="figures"' in html.split('id="figure-list"', 1)[0].rsplit("<ul", 1)[1]
    assert "is-list" not in html.split('id="figure-list"', 1)[0].rsplit("<ul", 1)[1]
    assert "figure-view-list" in script
    assert 'classList.toggle("is-list"' in script
    assert "grid-template-columns: 1fr" in list_rule
    assert "background: #f4ece7" in switch
    assert "background: #fff" in pressed


def test_dashboard_figure_does_not_borrow_a_picture_from_its_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    cover = tmp_path / "covers" / "stories" / "frog.mp3"
    cover.mkdir(parents=True)
    (cover / "cover.png").write_bytes(PNG)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "Frog"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog.mp3"\n'
        '    title: "The Frog Prince"\n'
    )
    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                covers=tmp_path / "covers",
                assign_catalog=PathCatalog(catalog_path),
            )
        )
        .get("/figures")
        .text
    )
    card = html.split('data-bound="yes"', 1)[1].split("</li>", 1)[0]

    assert "/library/cover/" not in card
    assert 'src="/mark.svg"' in card


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
    assert 'aria-label="Change picture"' in page
    assert 'aria-label="Upload picture"' not in page
    assert 'aria-label="Save picture"' not in page

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


def test_dashboard_figure_picture_changes_from_the_image(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tags:\n  - uid: "04aabbccddeeff"\n    name: "Frog"\ntracks: []\n')
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
    card = html.split(">Frog<", 1)[0].rsplit("<li", 1)[1] + html.split(">Frog<", 1)[1].split("</li>", 1)[0]

    assert 'aria-label="Upload picture"' not in card
    assert 'aria-label="Save picture"' not in card
    assert 'action="/figures/cover"' in card
    assert 'aria-label="Change picture"' in card
    assert 'onchange="this.form.submit()"' in card
    assert 'name="uid" value="04aabbccddeeff"' in card


def test_dashboard_figures_panels_control_playback_and_register(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
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
    assert 'href="/library?uid=04aabbccddeeff#assign"' in deck
    assert "Edit Mapping" in deck
    assert "Register this figure" in scan
    assert 'name="register" value="on"' in scan

    paused = client.post("/play", data={"return": "/figures"}, follow_redirects=False)
    assert paused.status_code == 303
    assert paused.headers["location"] == "/figures?notice=paused"

    nxt = client.post("/play/next", data={"return": "/figures"}, follow_redirects=False)
    assert nxt.status_code == 303
    assert nxt.headers["location"].startswith("/figures?notice=")
    assert player.playing_uid() == "04bbccddeeff00"


def test_dashboard_figures_live_deck_matches_the_player_sheet(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog
    from romini.fakes import FakePlayer

    library = tmp_path / "library"
    (library / "stories").mkdir(parents=True)
    (library / "stories" / "frog.mp3").write_bytes(b"id3")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "tags:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    name: "The Gruffalo"\n'
        "tracks:\n"
        '  - uid: "04aabbccddeeff"\n'
        '    path: "stories/frog.mp3"\n'
        '    title: "Deep Dark Wood"\n'
        '    artist: "Julia Donaldson"\n'
    )
    player = FakePlayer()
    player.play(str(library / "stories" / "frog.mp3"), position_sec=12, uid="04aabbccddeeff")
    html = (
        TestClient(
            create_dashboard(
                storage=DiskStorage(library),
                assign_catalog=PathCatalog(catalog_path),
                player=player,
                mixer=FakeMixer(level=65),
            )
        )
        .get("/figures")
        .text
    )
    deck = html.split('aria-label="Live physical deck"', 1)[1].split("</section>", 1)[0]

    assert deck.index('class="player-sheet"') < deck.index('class="deck-controls"')
    assert "ISO 14443-A Detected" in deck
    assert "UID: 04:AA:BB:CC:DD:EE:FF" in deck
    assert "Bedtime Story" in deck
    assert "Julia Donaldson Collection" in deck
    assert 'class="now-line"' in deck
    assert "65% Safe Max" in deck
    assert 'class="story-progress"' in deck
    assert 'class="edit-mapping"' in deck
    sheet = html.split(".player-sheet {", 1)[1].split("}", 1)[0]
    assert "border-radius" in sheet


def test_dashboard_figure_list_keeps_each_row_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    specs = html.split(".figures.is-list .figure-specs {", 1)[1].split("}", 1)[0]
    values = html.split(".figures.is-list .figure-specs dd {", 1)[1].split("}", 1)[0]
    foot = html.split(".figures.is-list .figure-foot {", 1)[1].split("}", 1)[0]
    hint = html.split(".figures.is-list .figure-foot .hint {", 1)[1].split("}", 1)[0]

    assert "min-width: 0" in specs
    assert "overflow: hidden" in specs
    assert "text-overflow: ellipsis" in values
    assert "justify-content: flex-end" in foot
    assert "text-align: right" in hint


def test_dashboard_figures_deck_mark_shrinks_and_the_sheet_fills_the_reader() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    ring = html.split(".hero-dock .dock-ring {", 1)[1].split("}", 1)[0]
    sheet = html.split(".hero-dock .player-sheet {", 1)[1].split("}", 1)[0]

    assert "width: 9rem" in ring
    assert "height: 9rem" in ring
    assert "flex: 1" in sheet


def test_dashboard_figures_deck_and_reader_share_the_same_row_height() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    rule = html.split(".studio:has(.live-deck) {", 1)[1].split("}", 1)[0]

    assert "align-items: stretch" in rule
    assert "align-items: start" not in rule


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
    mapped = cards.split("Mapped figures", 1)[1].split("Audio Track Library", 1)[0]
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
    radio = html.split('value="04ffeeddccbbaa"', 1)[1].split(">", 1)[0]

    assert "checked" in radio
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


def test_dashboard_figures_deck_pads_the_story_sheet() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    sheet = html.split(".hero-dock .player-sheet {", 1)[1].split("}", 1)[0]
    shell = html.split(".hero-dock.deck {", 1)[1].split("}", 1)[0]
    controls = html.split(".hero-dock .deck-controls {", 1)[1].split("}", 1)[0]

    assert "padding: 1.25rem 1.4rem" in sheet
    assert "background: #fff" in sheet
    assert "background: transparent" in shell
    assert "margin-top: auto" not in controls


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
