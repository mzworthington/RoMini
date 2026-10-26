from pathlib import Path

from romini.composition.dashboard.packs import (
    character_slug_list,
    current_pack,
    list_saved_characters,
    list_saved_stories,
    load_open_character,
    load_story_notes,
    spoken_file_name,
)
from romini.composition.story_audio import load_voices
from romini.composition.story_draft import listen_length_label, parse_duration_seconds

_NOTE_KEYS = ("title", "characters", "interests", "outline", "script", "character_slugs", "duration_seconds")


def story_context(page: str, stories: Path | None, characters: Path | None) -> dict[str, object]:
    bundle = _bundle(page, stories, characters)
    notes = bundle["notes"]
    character = bundle["opened_character"]
    duration = parse_duration_seconds(notes.get("duration_seconds"))
    return {
        "characters": notes["characters"],
        "outline": notes["outline"],
        "script": notes["script"],
        "story_title": notes["title"],
        "duration_seconds": duration,
        "story_length_label": listen_length_label(duration_seconds=duration),
        "spoken_file": bundle["spoken_file"],
        "opened_story_slug": bundle["opened_story_slug"],
        "stories_root": str(stories) if stories else "",
        "saved_stories": bundle["saved_stories"],
        "saved_characters": bundle["saved_characters"],
        "selected_character_slugs": character_slug_list(notes),
        "character_name": character["name"],
        "character_background": character["background"],
        "opened_character_slug": character["slug"],
        "voices": bundle["voices"],
    }


def _bundle(page: str, stories: Path | None, characters: Path | None) -> dict[str, object]:
    if page not in {"stories", "characters"}:
        return _empty_bundle()
    return {
        "notes": load_story_notes(stories),
        "opened_story_slug": _opened_slug(stories),
        "opened_character": load_open_character(characters),
        "saved_stories": list_saved_stories(stories),
        "saved_characters": list_saved_characters(characters),
        "spoken_file": spoken_file_name(stories),
        "voices": load_voices(),
    }


def _empty_bundle() -> dict[str, object]:
    return {
        "notes": {key: "" for key in _NOTE_KEYS},
        "opened_story_slug": "",
        "opened_character": {"name": "", "background": "", "slug": ""},
        "saved_stories": [],
        "saved_characters": [],
        "spoken_file": "",
        "voices": [],
    }


def _opened_slug(stories: Path | None) -> str:
    if stories is None:
        return ""
    pack = current_pack(stories)
    if pack == stories:
        return ""
    return pack.name
