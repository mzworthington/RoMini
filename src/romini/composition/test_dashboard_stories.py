from dataclasses import dataclass, field
from pathlib import Path

import pytest

from romini.composition.dashboard import create_dashboard

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
        assert '<h2 class="page-title">Story Studio</h2>' in html
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


def test_create_new_story_lives_in_saved_stories() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/stories").text
    toolbar = html.split('class="page-actions studio-toolbar"', 1)[1].split('class="studio"', 1)[0]
    saved = html.split("<h2>Saved stories</h2>", 1)[1].split("</section>", 1)[0]

    assert ">Create New Story<" in saved
    assert 'action="/stories/new"' in saved
    assert 'class="plus-glyph"' in saved
    assert ">Create New Story<" not in toolbar


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

    title = '<h2 class="page-title">Story Studio</h2>'
    assert title in client.get("/stories").text
    assert title in client.get("/characters").text


def test_dashboard_characters_page_has_labelled_create_fields() -> None:
    from fastapi.testclient import TestClient

    html = TestClient(create_dashboard(storage=FakeStorage(free_bytes=1024))).get("/characters").text

    assert "<h2>Add a character</h2>" in html
    assert 'for="character-name"' in html
    assert ">Name<" in html
    assert 'for="character-background"' in html
    assert "Background and history" in html


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

    assert ">Create New Story<" in saved.split("<h2>Saved stories</h2>", 1)[1]
    assert 'value="Romy"' not in html
    assert 'type="hidden" name="slug"' not in html
    assert ">Edit<" in html


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

    assert ">Create New Story<" in saved.split("<h2>Saved stories</h2>", 1)[1]
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
    assert "Upload image" not in library
    served = client.get("/library/cover/station.mp3")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.content == PNG


def test_dashboard_story_picture_is_set_from_the_row(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from romini.composition.dashboard import PathCatalog

    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text('tracks:\n  - path: "bedtime.mp3"\n    title: "Bedtime"\n')
    covers = tmp_path / "covers"
    storage = FakeStorage(free_bytes=1024)
    storage.put("bedtime.mp3", b"id3")
    client = TestClient(create_dashboard(storage=storage, covers=covers, assign_catalog=PathCatalog(catalog_path)))
    page = client.get("/library").text
    table = page.split("<caption>Library</caption>", 1)[1].split("</table>", 1)[0]

    row = table.split(">Bedtime<", 1)[0].rsplit("<tr", 1)[1] + table.split(">Bedtime<", 1)[1].split("</tr>", 1)[0]

    assert "Upload image" not in page
    assert 'aria-label="Upload cover"' not in row
    assert 'aria-label="Save cover"' not in row
    assert 'aria-label="Reassign figurine"' not in row
    assert 'action="/library/cover"' in row
    assert 'aria-label="Change picture"' in row
    assert 'onchange="this.form.submit()"' in row
    assert 'class="cover"' in row.split('aria-label="Change picture"', 1)[0]
    assert ">Edit<" in row
    assert 'data-path="bedtime.mp3"' in row
    assert 'data-title="Bedtime"' in row
    assert "data-title" in page.split("function fillAssign", 1)[1]


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

    now = html.split('aria-label="Now playing"', 1)[1].split("</section>", 1)[0]
    assert 'class="cover"' not in now


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


def test_story_pack_saves_and_reloads_the_script(tmp_path: Path) -> None:
    from romini.composition.dashboard.packs import load_story_notes, write_story_notes

    write_story_notes(
        tmp_path,
        title="Frog",
        characters="Romy",
        interests="",
        outline="",
        script="Once upon a time",
    )
    notes = load_story_notes(tmp_path)

    assert notes["title"] == "Frog"
    assert notes["script"] == "Once upon a time"


def test_character_pack_saves_and_reloads_the_open_character(tmp_path: Path) -> None:
    from romini.composition.dashboard.packs import load_open_character, write_character

    write_character(tmp_path, name="Romy", background="Likes frogs")
    opened = load_open_character(tmp_path)

    assert opened["name"] == "Romy"
    assert opened["background"] == "Likes frogs"
