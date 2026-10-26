from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.media import library_paths
from romini.composition.dashboard.packs import (
    current_pack,
    load_story_notes,
    open_story_pack,
    record_spoken_track,
    spoken_file_name,
    story_slug,
    unique_track_filename,
)
from romini.composition.dashboard.responses import QuietNotices, notice, vendor_detail
from romini.composition.dashboard.studio_keys import elevenlabs_api_key, studio_keys
from romini.composition.story_audio import ElevenLabsSpeech, http_post, load_voices
from romini.features.library.add_track import add_track


@dataclass
class _Speech:
    voice_id: str
    key: str
    script: str
    notes: dict[str, str]


async def speak_story(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    open_story_pack(ctx.stories, str(form.get("slug") or "").strip())
    prepared = _prepare_speech(ctx, form)
    if isinstance(prepared, RedirectResponse):
        return prepared
    audio = _speak(ctx, prepared)
    if isinstance(audio, RedirectResponse):
        return audio
    return _store_spoken(ctx, prepared, audio)


def _prepare_speech(ctx: DashboardCtx, form: object) -> _Speech | RedirectResponse:
    keys = studio_keys(ctx.secrets, ctx.box_secrets)
    voice_id = _voice_id(form)
    key = elevenlabs_api_key(keys["ELEVENLABS_API_KEY"])
    refused = _speech_refusal(ctx, keys["ELEVENLABS_API_KEY"], key, voice_id)
    if refused is not None:
        return refused
    notes = load_story_notes(ctx.stories)
    script = notes["script"].strip()
    if not script:
        ctx.note("speak", "Speak failed (no script)", headline="Speak failed")
        return notice("/stories", "speak-needed")
    return _Speech(voice_id=voice_id, key=key, script=script, notes=notes)


def _voice_id(form: object) -> str:
    named = load_voices()
    allowed = {voice["id"] for voice in named}
    chosen = str(form.get("voice_id") or "").strip()
    if chosen in allowed:
        return chosen
    if named:
        return named[0]["id"]
    return ""


def _speech_refusal(ctx: DashboardCtx, raw_key: str, key: str, voice_id: str) -> RedirectResponse | None:
    if raw_key and not key:
        ctx.note("speak", "Speak failed (key id)", headline="Speak failed")
        return notice("/stories", "speak-key-id")
    if not key or not voice_id:
        ctx.note("speak", "Speak failed (no key)", headline="Speak failed")
        return notice("/stories", "speak-needed")
    return None


def _speak(ctx: DashboardCtx, prepared: _Speech) -> bytes | RedirectResponse:
    speaker = ctx.speech or ElevenLabsSpeech(api_key=prepared.key, post=ctx.speak_post or http_post)
    try:
        return speaker.speak(text=prepared.script, voice_id=prepared.voice_id)
    except Exception as err:
        return _speak_failed(ctx, err)


def _speak_failed(ctx: DashboardCtx, err: Exception) -> RedirectResponse:
    ctx.note_failed("speak", "Speak", err)
    message = vendor_detail(err)
    if message:
        return notice("/stories", "speak-needed", message)
    return notice("/stories", "speak-needed")


def _store_spoken(ctx: DashboardCtx, prepared: _Speech, audio: bytes) -> RedirectResponse:
    pack = current_pack(ctx.stories)
    filename = _spoken_filename(ctx, pack, prepared.notes)
    if not _keep_audio(ctx, filename, audio):
        ctx.note("speak", "Speak failed (full)", headline="Speak failed")
        return notice("/stories", "full")
    _replace_pack_audio(pack, ctx.stories, filename, audio)
    record_spoken_track(pack, filename=filename, library_path=filename)
    ctx.note("speak", f"Spoke story {prepared.notes['title'] or filename}", headline="Story spoken")
    return notice("/stories", "spoke")


def _spoken_filename(ctx: DashboardCtx, pack: Path, notes: dict[str, str]) -> str:
    slug = pack.name if pack != ctx.stories else story_slug(notes["title"])
    return unique_track_filename(slug=slug, taken=set(library_paths(ctx.storage)), keep=spoken_file_name(ctx.stories))


def _keep_audio(ctx: DashboardCtx, filename: str, audio: bytes) -> bool:
    return add_track(
        audio=audio,
        filename=filename,
        storage=ctx.storage,
        notices=ctx.notices if ctx.notices is not None else QuietNotices(),
        catalog=ctx.catalog,
    )


def _replace_pack_audio(pack: Path, stories: Path, filename: str, audio: bytes) -> None:
    if pack != stories and pack.is_dir():
        for old in pack.iterdir():
            if old.is_file() and old.suffix.lower() == ".mp3" and old.name != filename:
                old.unlink()
    pack.mkdir(parents=True, exist_ok=True)
    (pack / filename).write_bytes(audio)
