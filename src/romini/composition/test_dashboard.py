from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import create_dashboard
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


def test_dashboard_shows_free_space() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/storage")

    assert response.status_code == 200
    assert response.json() == {"free_bytes": 1024}


def test_dashboard_switches_play_mode(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    settings = SqliteSettings(tmp_path / "state.sqlite")
    app = create_dashboard(storage=FakeStorage(free_bytes=1024), settings=settings)
    response = TestClient(app).put("/play-mode", json={"play_mode": "tap"})

    assert response.status_code == 204
    assert settings.play_mode() is PlayMode.TAP


def test_dashboard_page_titles_match_the_nav_labels() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))

    home = client.get("/").text
    figures = client.get("/figures").text
    library = client.get("/library").text
    stories = client.get("/stories").text
    settings = client.get("/settings").text

    assert '<h2 class="page-title">Live Player</h2>' in home
    assert "<title>Live Player · RoMini</title>" in home
    assert '<h2 class="page-title">Figures &amp; Tags</h2>' in figures
    assert "<title>Figures &amp; Tags · RoMini</title>" in figures
    assert '<h2 class="page-title">Audio Library</h2>' in library
    assert "<title>Audio Library · RoMini</title>" in library
    assert '<h2 class="page-title">Story Studio</h2>' in stories
    assert "<title>Story Studio · RoMini</title>" in stories
    assert '<h2 class="page-title">System &amp; Hardware</h2>' in settings
    assert "<title>System &amp; Hardware · RoMini</title>" in settings


def test_dashboard_live_player_is_playback_without_the_old_jump_list() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert 'class="page-title"' in html
    assert '<h2 class="page-title">Live Player</h2>' in html.split("<main", 1)[1]
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

    header = html.split("<header", 1)[1].split("</header>", 1)[0]
    pills = header.split('class="status-pills"', 1)[1].split("</ul>", 1)[0]

    assert "WiFi N/A" in pills
    assert "Wi-Fi Not reported" not in pills


def test_dashboard_mobile_nav_scrolls_inside_the_card() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    narrow = html.split("@media (max-width: 960px) {", 1)[1].split("@media", 1)[0]
    nav = narrow.split('.topbar nav[aria-label="Dashboard"] {', 1)[1].split("}", 1)[0]
    track = narrow.split('.topbar nav[aria-label="Dashboard"] ul {', 1)[1].split("}", 1)[0]

    assert "min-width: 0" in nav
    assert "max-width: 100%" in nav
    assert "width: 100%" in track


def test_dashboard_mobile_nav_labels_stay_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    link = html.split('nav[aria-label="Dashboard"] a {', 1)[1].split("}", 1)[0]
    narrow = html.split("@media (max-width: 960px) {", 1)[1].split("@media", 1)[0]

    assert "white-space: nowrap" in link
    assert "flex: none" in link
    assert "overflow-x: auto" in narrow


def test_dashboard_header_has_no_scan_tag_button() -> None:
    from fastapi.testclient import TestClient

    header = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
        .get("/")
        .text.split("<header", 1)[1]
        .split("</header>", 1)[0]
    )

    assert "Scan tag" not in header
    assert 'class="scan"' not in header


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
    assert pills.index("Cap 75") < pills.index('href="/settings#network"')
    assert "free" not in pills


def test_dashboard_status_pills_read_as_chips() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=40))).get("/").text
    rule = html.split(".status-pills a {", 1)[1].split("}", 1)[0]

    assert "text-decoration: none" in rule
    assert "color: inherit" in rule


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
    assert "Volume cap" in html
    assert "Screen-free domestic audio for growing minds." in html
    assert "Nothing is playing" in html


def test_dashboard_live_player_hides_controls_the_box_does_not_drive() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "−15" not in html
    assert "+15" not in html
    assert "Night light" not in html
    assert "Extend +15m" not in html


def test_dashboard_delete_restart_and_reboot_ask_first(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    class Power:
        def restart(self) -> None:
            return None

        def reboot(self) -> None:
            return None

        def poweroff(self) -> None:
            return None

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path, power=Power()))
    client.post("/stories", data={"story_title": "The little station"})
    stories = client.get("/stories").text
    delete_form = stories.split('action="/stories/delete"', 1)[0].rsplit("<form", 1)[1]
    settings = client.get("/settings").text
    restart_form = settings.split('value="restart"', 1)[0].rsplit("<form", 1)[1]
    reboot_form = settings.split('value="reboot"', 1)[0].rsplit("<form", 1)[1]

    assert "confirm(" in delete_form
    assert "confirm(" in restart_form
    assert "confirm(" in reboot_form


def test_dashboard_scrubber_draws_many_thin_strokes() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    wave = html.split('class="waveform"', 1)[1].split('class="transport"', 1)[0]
    from jinja2 import Environment, FileSystemLoader

    templates = Path(__file__).parent / "dashboard" / "templates"
    css = Environment(loader=FileSystemLoader(templates)).get_template("dashboard.css").render()

    assert wave.count('<span style="height:') >= 48
    assert "flex: 0 0 2px" in css


def test_dashboard_home_shows_free_space() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "1.0 KB free" in response.text
    assert "free free" not in response.text


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
    assert 'for="file"' in library
    assert 'class="play-mode"' in settings
    assert 'name="play_mode"' in settings
    assert 'value="presence"' in settings
    assert 'value="tap"' in settings


def test_dashboard_home_has_upload_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/library")

    assert 'action="/tracks"' in response.text
    assert 'type="file"' in response.text


def test_dashboard_home_has_assign_form() -> None:
    from fastapi.testclient import TestClient

    app = create_dashboard(storage=FakeStorage(free_bytes=1024))
    response = TestClient(app).get("/library")

    assert "No stories yet. Upload a track, then assign a figure." in response.text
    assert 'action="/assign"' not in response.text


def test_dashboard_library_header_has_no_storage_or_upload_actions() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    actions = html.split('class="page-head"', 1)[1].split("{% block", 1)[0]
    if 'class="page-actions"' in actions:
        actions = actions.split('class="page-actions"', 1)[1].split("</div>", 1)[0]

    assert "Storage Analysis" not in actions
    assert "Upload New Story" not in actions
    assert "Upload Audio Files" not in actions


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
    assert "<th>Figure</th>" in response.text
    assert "<th>Story Title</th>" in response.text
    assert "<th>Author / Narrator</th>" in response.text
    assert "stories/frog-prince.mp3" in response.text


def test_dashboard_active_preview_badge_stays_on_one_line() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text
    badge = html.split(".preview-badge {", 1)[1].split("}", 1)[0]

    assert "white-space: nowrap" in badge
    assert "flex-shrink: 0" in badge


def test_dashboard_home_lays_out_actions_in_a_flex_board_below_library() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'class="board"' in html
    board = html.index('class="board"')
    upload = html.index("Drag audio files directly onto this panel")
    library = html.index('<h2 class="catalog-title">Library</h2>')
    assert board < upload < library
    assert "flex-wrap: wrap" in html


def test_dashboard_home_has_place_form_for_each_track(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    @dataclass
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


def test_dashboard_place_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class FakePad:
        def place(self, uid: str) -> None:
            return

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), pad=FakePad())).post(
        "/place/04aabbccddeeff",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/library?notice=placed"


def test_dashboard_register_mode_off_returns_with_notice() -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class FakeRegister:
        assign_mode = True

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).post(
        "/register-mode", data={"register": "off"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/figures?notice=register-off"


def test_dashboard_home_has_register_form() -> None:
    from fastapi.testclient import TestClient

    @dataclass
    class FakeRegister:
        assign_mode = False

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), register=FakeRegister())).get("/figures").text
    )

    scan = html.split('aria-label="Quick reader sensor"', 1)[1].split("</section>", 1)[0]
    assert 'action="/register-mode"' in scan
    assert 'name="register" value="on"' in scan
    assert "Register this figure" in scan
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


def test_dashboard_tables_right_align_last_column_and_stretch_inputs() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text

    assert "th:last-child, td:last-child { text-align: right; width: 1%; white-space: nowrap; }" in html
    assert "td:has(input) { width: 100%; }" in html


def test_dashboard_home_shows_notice_after_action() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text

    assert 'role="status"' in html
    assert "Figure assigned" in html


def test_dashboard_notice_overlays_the_page_and_can_dismiss() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/?notice=assigned").text
    main = html.split("<main", 1)[1].split("</main>", 1)[0]

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


def test_dashboard_home_hides_volume_without_a_mixer() -> None:
    from fastapi.testclient import TestClient

    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
    home = client.get("/").text
    html = client.get("/settings").text

    assert ">Volume<" not in home
    assert 'action="/volume"' not in home
    assert ">Volume<" not in html
    assert 'action="/volume"' not in html


def test_dashboard_volume_form_returns_to_settings_with_notice() -> None:
    from fastapi.testclient import TestClient

    response = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=10))).post(
        "/volume", data={"step": "up"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/settings?notice=volume"


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


def test_story_studio_header_has_no_new_character_button() -> None:
    from fastapi.testclient import TestClient

    actions = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024)))
        .get("/stories")
        .text.split('class="page-actions studio-toolbar"', 1)[1]
        .split('class="studio"', 1)[0]
    )

    assert ">New Character<" not in actions
    assert 'action="/characters/new"' not in actions


def test_story_studio_header_actions_follow_the_design() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text
    actions = html.split('class="page-actions studio-toolbar"', 1)[1].split("<main", 1)[0]

    assert "Gemini 3.6 Flash" in actions
    assert "ElevenLabs v3" in actions
    assert ">API Keys<" in actions
    assert 'class="key-glyph"' in actions


def test_dashboard_scan_tag_stays_on_one_line_and_system_nav_names_hardware() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    primary = html.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]

    assert ">System &amp; Hardware<" in primary


def test_dashboard_skip_link_dimmed_power_and_story_step_copy(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    home = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    stories = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), stories=tmp_path))
    stories.post("/stories", data={"story_title": "The little station", "script": ""})
    studio = stories.get("/stories").text

    assert 'class="skip" href="#main"' in home
    assert 'id="main"' in home
    assert "opacity: 0.45" in home
    assert "Insert softly" in studio
    assert "Save a script to speak it." in studio


def test_dashboard_nav_leads_with_the_live_player_and_status_opens_its_page() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(
            create_dashboard(
                storage=FakeStorage(free_bytes=1024),
                battery=FakeBattery(percent=72),
                mixer=FakeMixer(level=40, ceiling=75),
            )
        )
        .get("/")
        .text
    )
    primary = html.split('<nav aria-label="Dashboard">', 1)[1].split("</nav>", 1)[0]
    pills = html.split('class="status-pills"', 1)[1].split("</ul>", 1)[0]

    assert primary.index(">Live Player<") < primary.index(">Figures &amp; Tags<")
    assert primary.index(">Figures &amp; Tags<") < primary.index(">Audio Library<")
    assert 'href="/settings#pack"' in pills
    assert 'href="/#volume"' in pills
    assert 'href="/settings#network"' in pills
    assert 'id="volume"' in html
    assert 'id="pack"' in TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text
    assert 'id="network"' in TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/settings").text


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


def test_dashboard_nav_has_stories_without_a_separate_write_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text

    assert 'href="/stories"' in html
    assert ">Story Studio<" in html
    assert 'href="/write"' not in html
    assert ">Write<" not in html


def test_dashboard_nav_has_characters_page() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/characters").text

    assert 'href="/characters"' in html
    assert ">Characters<" in html
    assert 'aria-current="page"' in html


def test_dashboard_busy_script_disables_every_button_and_blocks_a_second_submit() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/library").text

    assert 'document.querySelectorAll("button")' in html
    assert "preventDefault" in html
    assert "disabled = true" in html


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


def test_dashboard_does_not_treat_an_elevenlabs_key_id_as_set(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    secrets = tmp_path / "studio.env"
    secrets.write_text("ELEVENLABS_API_KEY=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n")
    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), secrets=secrets)).get("/settings").text

    assert "ElevenLabs key is set" not in html
    assert "starts with sk_" in html


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
    assert "Choose audio files" in library
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
    assert 'class="play-modes"' in settings
    assert "<h2>Volume</h2>" in settings


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
    for index, minute in enumerate(range(12)):
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
    assert stream.count("activity-mark") == 10
    assert "<strong>Event 11</strong>" in stream
    assert "<strong>Event 1</strong>" not in stream
    assert 'href="/settings#audit"' in html
    assert "View Complete Hardware Journal" in html


def test_dashboard_hash_links_scroll_to_the_named_section(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tags:\n  - uid: "04aabbccddeeff"\n    name: "Frog"\n')
    client = TestClient(
        create_dashboard(storage=FakeStorage(free_bytes=1024), assign_catalog=PathCatalog(catalog_path))
    )
    figures = client.get("/figures").text
    settings = client.get("/settings").text

    assert 'href="/settings#audit"' in figures
    assert 'id="audit"' in settings
    assert 'href="/library?uid=04aabbccddeeff#assign"' in figures
    assert "scrollIntoView" in figures
    assert "decodeURIComponent(landed.hash.slice(1))" in figures


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
    figures = html.index("<h2>Figures</h2>")
    assert scan < figures
    assert "<h2>Present a figure</h2>" not in html
    assert "<h2>Register figures</h2>" not in html
    assert 'action="/tracks"' not in html
    assert 'action="/assign"' not in html
    assert "<h2>Library</h2>" not in html


def test_dashboard_playing_sheet_stacks_on_a_phone() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/figures").text
    blocks = html.split("@media (max-width: 40rem) {")[1:]
    narrow = next(block.split("@media", 1)[0] for block in blocks if ".hero-dock .hero-row" in block)
    row = narrow.split(".hero-dock .hero-row {", 1)[1].split("}", 1)[0]
    title = narrow.split(".hero-dock .deck-title {", 1)[1].split("}", 1)[0]
    times = narrow.split(".hero-dock .scrub-times {", 1)[1].split("}", 1)[0]
    controls = narrow.split(".hero-dock .deck-controls {", 1)[1].split("}", 1)[0]
    volume = narrow.split('.hero-dock .deck-volume input[type="range"] {', 1)[1].split("}", 1)[0]

    assert "flex-direction: column" in row
    assert "overflow-wrap: anywhere" in title
    assert "flex-wrap: wrap" in times
    assert "column-gap" in times
    assert "flex-direction: column" in controls
    assert "flex: 1" in volume


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


def test_dashboard_live_player_plate_shows_the_mark() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text
    plate = html.split('aria-label="On the plate"', 1)[1].split("</section>", 1)[0]

    assert 'class="plate-mark"' in plate
    assert 'src="/mark.svg"' in plate


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

    assert quiet.count('class="seek-glyph"') == 1


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


def test_dashboard_preview_player_is_labelled() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024, files={"frog.mp3": b"id3"})))
        .get("/library")
        .text
    )

    assert 'aria-label="Preview"' in html


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


def test_dashboard_emergency_mute_sets_the_mixer_to_zero() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=40)
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer))

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
    table = library.split("<caption>Library</caption>", 1)[1].split("</table>", 1)[0]
    assert 'src="/logo.svg"' in table
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
    now = playing.split('aria-label="Now playing"', 1)[1].split("</section>", 1)[0]
    assert 'class="cover"' not in now


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


def test_dashboard_home_has_no_bedtime_fade_or_emergency_mute() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=40))).get("/").text

    assert "Bedtime fade" not in html
    assert "Emergency mute" not in html
    assert 'action="/mute"' not in html


def test_dashboard_home_has_no_stop_and_eject_button() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/").text

    assert "Stop &amp; Eject" not in html
    assert 'action="/safety/eject"' not in html


def test_dashboard_home_keeps_the_volume_readout_and_eject() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=40, ceiling=75)))
        .get("/")
        .text
    )

    assert "Volume cap" in html
    assert "40 of 75" in html
    assert "Raspberry Pi Safety" not in html
    assert "Sleep in 30m" not in html
    assert 'action="/safety/beep"' not in html
    assert "dB" not in html


def test_dashboard_home_volume_cap_sets_the_level() -> None:
    from fastapi.testclient import TestClient

    mixer = FakeMixer(level=40, ceiling=75)
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=mixer))
    html = client.get("/").text
    guard = html.split(">Volume cap<", 1)[1].split('class="guard-scale"', 1)[0]

    assert 'action="/volume"' in guard
    assert 'name="return" value="/"' in guard
    assert 'name="level"' in guard
    assert 'type="range"' in guard
    assert 'max="75"' in guard
    assert 'value="40"' in guard

    response = client.post("/volume", data={"level": "20", "return": "/"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?notice=volume"
    assert mixer.level == 20


def test_dashboard_home_volume_cap_shows_a_drag_thumb() -> None:
    from fastapi.testclient import TestClient

    html = (
        TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), mixer=FakeMixer(level=40, ceiling=75)))
        .get("/")
        .text
    )
    guard = html.split(">Volume cap<", 1)[1].split('class="guard-scale"', 1)[0]

    assert 'class="guard-thumb"' in guard
    assert "--cap: 53%" in guard


def test_dashboard_stop_and_eject_stops_playback() -> None:
    from fastapi.testclient import TestClient

    from romini.fakes import FakePlayer

    player = FakePlayer()
    player.play("story.mp3", position_sec=12.0, uid="04aabbccddeeff")
    client = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024), player=player))

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


def test_studio_keys_writes_and_reloads_a_gemini_key(tmp_path: Path) -> None:
    from romini.composition.dashboard.studio_keys import studio_keys, write_studio_keys

    secrets = tmp_path / "studio.env"
    write_studio_keys(secrets, gemini_key="gem-secret", elevenlabs_key="", elevenlabs_voices="")
    loaded = studio_keys(secrets)

    assert loaded["GEMINI_API_KEY"] == "gem-secret"


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
