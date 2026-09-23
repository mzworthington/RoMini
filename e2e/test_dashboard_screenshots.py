"""Capture every parent-dashboard page and the sim harness into docs/images.

Not part of `make test`. Refresh with `make screenshots`.
"""

import io
import wave
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from romini.adapters.sqlite.audit import SqliteAudit
from romini.adapters.sqlite.settings import SqliteSettings
from romini.composition.dashboard import DiskStorage, PathCatalog, create_dashboard
from romini.composition.dashboard import shared as dashboard_shared
from romini.composition.dashboard.server import start_dashboard
from romini.composition.dashboard.shared import write_character, write_story_notes
from romini.composition.http import start_sim_http
from romini.composition.mixer import MemoryMixer
from romini.fakes import FakePlayer
from romini.features.audit.record import record_event

REPO = Path(__file__).resolve().parents[1]
IMAGES = REPO / "docs" / "images"
PNG = b"\x89PNG\r\n\x1a\n"

PAGES = (
    ("/", "home.png"),
    ("/figures", "figures.png"),
    ("/library", "library.png"),
    ("/stories/the-frog-prince", "stories.png"),
    ("/characters/romy", "characters.png"),
    ("/settings", "settings.png"),
)


@dataclass
class ShotBattery:
    percent: int | None = 86
    volts: float | None = 4.12
    flow: str | None = "charging"


class ShotRegister:
    assign_mode = False


class ShotPad:
    def place(self, uid: str) -> None:
        return


class StoryboxDisk:
    """Sample Pi disk so docs shots are not this laptop's volume or pytest path."""

    def __init__(self, inner: DiskStorage) -> None:
        self._inner = inner
        self.free_bytes = 11 * 1024**3
        self.total_bytes = 16 * 1024**3
        self.root = "/var/lib/romini/library"

    def put(self, filename: str, audio: bytes) -> None:
        self._inner.put(filename, audio)

    def paths(self) -> list[str]:
        return self._inner.paths()

    def get(self, filename: str) -> bytes | None:
        return self._inner.get(filename)


def _storybox_host() -> dict[str, str]:
    return {
        "hostname": "romini",
        "address": "192.168.1.40",
        "cpu_temp": "48°C",
        "load": "0.21",
        "memory": "612 MB / 4096 MB",
        "uptime": "2h 14m",
        "wifi": "House",
    }


def _wav(seconds: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000 * seconds)
    return buffer.getvalue()


def _seed(root: Path) -> None:
    library = root / "library"
    library.mkdir()
    (library / "frog-prince.mp3").write_bytes(_wav(75))
    (library / "evening-lullaby.mp3").write_bytes(_wav(40))
    (root / "catalog.yaml").write_text(
        "\n".join(
            [
                "tags:",
                '  - uid: "04aabbccddeeff"',
                "    name: Frog Prince",
                '  - uid: "04bbccddeeff00"',
                "    name: Moon Bear",
                "tracks:",
                '  - uid: "04aabbccddeeff"',
                '    path: "frog-prince.mp3"',
                '    title: "The Frog Prince"',
                '    artist: "RoMini"',
                '  - uid: ""',
                '    path: "evening-lullaby.mp3"',
                '    title: "Evening Lullaby"',
                '    artist: "RoMini"',
                "",
            ]
        )
    )
    stories = root / "stories"
    write_story_notes(
        stories,
        title="Evening Lullaby",
        characters="",
        interests="soft rain",
        outline="A bear counts stars until the room is quiet.",
        script="",
        character_slugs=["romy"],
        duration_seconds=120,
    )
    write_story_notes(
        stories,
        title="The Frog Prince",
        characters="",
        interests="a golden ball and a deep well",
        outline="Romy drops her ball, and the frog asks to come home for supper.",
        script="Once there was a frog who kept a golden ball.\n[softly] He waited by the well until Romy came back.",
        character_slugs=["romy", "the-frog"],
        duration_seconds=180,
    )
    characters = root / "characters"
    write_character(
        characters,
        name="Romy",
        background="Lives in the storybox house and likes frogs, wells, and one more chapter.",
    )
    write_character(
        characters,
        name="The Frog",
        background="A patient frog by the well who keeps promises and speaks softly at bedtime.",
    )
    state = root / "state.sqlite"
    audit = SqliteAudit(state)
    moment = datetime(2026, 9, 20, 19, 4, tzinfo=UTC)
    events = (
        ("boot", "Storybox ready on the house LAN", "Box ready"),
        ("upload", "Stored frog-prince.mp3", "Track stored"),
        ("assign", "Frog Prince plays The Frog Prince", "Figure assigned"),
        ("place", "Frog Prince on the plate", "Figure placed"),
    )
    for index, (action, summary, headline) in enumerate(events):
        when = moment + timedelta(minutes=index)
        record_event(audit, action=action, summary=summary, headline=headline, clock=lambda when=when: when)


def _shot(page, path: Path) -> None:
    page.screenshot(path=path, full_page=True)
    data = path.read_bytes()
    assert data.startswith(PNG)
    assert len(data) > 5_000


def test_dashboard_pages_are_saved_under_docs_images(tmp_path: Path) -> None:
    sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright
    _seed(tmp_path)
    player = FakePlayer()
    player.play("frog-prince.mp3", position_sec=42, uid="04aabbccddeeff")
    original_host = dashboard_shared.read_host_facts
    dashboard_shared.read_host_facts = _storybox_host
    app = create_dashboard(
        storage=StoryboxDisk(DiskStorage(tmp_path / "library")),
        assign_catalog=PathCatalog(tmp_path / "catalog.yaml"),
        settings=SqliteSettings(tmp_path / "state.sqlite"),
        pad=ShotPad(),
        register=ShotRegister(),
        mixer=MemoryMixer(level=40, ceiling=80),
        battery=ShotBattery(),
        stories=tmp_path / "stories",
        covers=tmp_path / "covers",
        characters=tmp_path / "characters",
        secrets=tmp_path / "studio.env",
        player=player,
        audit=SqliteAudit(tmp_path / "state.sqlite"),
    )
    dashboard = start_dashboard(app, host="127.0.0.1", port=0)
    harness = start_sim_http(object(), host="127.0.0.1", port=0)
    IMAGES.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                device_scale_factor=1,
                color_scheme="light",
            )
            page = context.new_page()
            page.add_init_script(
                "document.addEventListener('DOMContentLoaded', () => {"
                " const style = document.createElement('style');"
                " style.textContent = ["
                " '*,*::before,*::after{animation:none!important;transition:none!important}',"
                " '.path-note{display:none!important}',"
                " ].join('');"
                " document.head.appendChild(style);"
                "});"
            )
            base = f"http://127.0.0.1:{dashboard.port}"
            for route, name in PAGES:
                response = page.goto(f"{base}{route}", wait_until="networkidle")
                assert response is not None and response.ok
                page.evaluate("document.fonts.ready")
                _shot(page, IMAGES / name)
            response = page.goto(f"{base}/settings", wait_until="networkidle")
            assert response is not None and response.ok
            audit = IMAGES / "audit.png"
            page.locator("#audit").screenshot(path=audit)
            assert audit.read_bytes().startswith(PNG)
            response = page.goto(f"{base}/stories/the-frog-prince", wait_until="networkidle")
            assert response is not None and response.ok
            speak = IMAGES / "ai-stories.png"
            page.locator("section.card").filter(has=page.get_by_role("heading", name="Speak the story")).screenshot(
                path=speak
            )
            assert speak.read_bytes().startswith(PNG)
            response = page.goto(f"http://127.0.0.1:{harness.port}/", wait_until="networkidle")
            assert response is not None and response.ok
            page.evaluate("document.fonts.ready")
            _shot(page, IMAGES / "test-harness.png")
            browser.close()
    finally:
        dashboard_shared.read_host_facts = original_host
        harness.close()
        dashboard.close()

    saved = {name for _, name in PAGES} | {"audit.png", "ai-stories.png", "test-harness.png"}
    assert saved <= {path.name for path in IMAGES.glob("*.png")}
