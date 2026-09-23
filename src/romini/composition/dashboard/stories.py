import shutil

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.shared import (
    DashboardCtx,
    character_slug_list,
    clear_current,
    current_pack,
    draft_character_text,
    elevenlabs_api_key,
    library_paths,
    load_story_notes,
    notice,
    open_story_pack,
    record_spoken_track,
    safe_character_slugs,
    spoken_file_name,
    story_slug,
    studio_keys,
    unique_track_filename,
    write_story_notes,
)
from romini.composition.story_audio import ElevenLabsSpeech, http_post, load_voices
from romini.composition.story_draft import GeminiScriptDraft, gemini_http_post, parse_duration_seconds
from romini.features.library.add_track import add_track


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    @app.get("/stories", response_model=None)
    def stories_page(request: Request) -> HTMLResponse | RedirectResponse:
        if ctx.stories is not None:
            pack = current_pack(ctx.stories)
            if pack != ctx.stories:
                dest = f"/stories/{pack.name}"
                if request.url.query:
                    dest = f"{dest}?{request.url.query}"
                return RedirectResponse(dest, status_code=303)
        return ctx.page(request, "stories.html", page="stories", page_title="Stories")

    @app.get("/stories/{slug}", response_class=HTMLResponse)
    def story_page(request: Request, slug: str) -> HTMLResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        open_story_pack(ctx.stories, slug)
        if current_pack(ctx.stories) != ctx.stories / slug:
            raise HTTPException(status_code=404)
        return ctx.page(request, "stories.html", page="stories", page_title="Stories")

    @app.get("/stories/{slug}/spoken")
    def preview_spoken(slug: str) -> FileResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        open_story_pack(ctx.stories, slug)
        pack = ctx.stories / slug
        if current_pack(ctx.stories) != pack:
            raise HTTPException(status_code=404)
        filename = spoken_file_name(ctx.stories)
        if not filename:
            raise HTTPException(status_code=404)
        path = pack / filename
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="audio/mpeg")

    @app.get("/write")
    def write_page() -> RedirectResponse:
        return RedirectResponse("/stories", status_code=303)

    @app.post("/stories", response_model=None)
    async def save_story_notes(request: Request) -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        pack = write_story_notes(
            ctx.stories,
            title=str(form.get("story_title") or ""),
            characters=str(form.get("characters") or ""),
            interests=str(form.get("interests") or ""),
            outline=str(form.get("outline") or ""),
            script=str(form.get("script") or ""),
            character_slugs=safe_character_slugs(list(form.getlist("character"))),
            duration_seconds=parse_duration_seconds(form.get("duration_seconds")),
        )
        title = str(form.get("story_title") or "").strip() or pack.name
        ctx.note("story", f"Saved story {title}", headline="Story saved")
        dest = f"/stories/{pack.name}" if pack != ctx.stories else "/stories"
        return notice(dest, "story")

    @app.post("/stories/open", response_model=None)
    async def open_story(request: Request) -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        open_story_pack(ctx.stories, slug)
        if slug:
            ctx.note("story", f"Opened story {slug}", headline="Story opened")
        return notice("/stories", "story")

    @app.post("/stories/new", response_model=None)
    def new_story() -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        clear_current(ctx.stories)
        return RedirectResponse("/stories", status_code=303)

    @app.post("/stories/delete", response_model=None)
    async def delete_story(request: Request) -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        form = await request.form()
        slug = str(form.get("slug") or "").strip()
        pack = ctx.stories / slug
        if (
            slug
            and slug not in {".", ".."}
            and "/" not in slug
            and "\\" not in slug
            and (pack / "story.yaml").is_file()
        ):
            if current_pack(ctx.stories) == pack:
                clear_current(ctx.stories)
            shutil.rmtree(pack)
            ctx.note("story", f"Deleted story {slug}", headline="Story deleted")
        return notice("/stories", "story")

    @app.post("/stories/draft", response_model=None)
    def draft_story() -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        key = studio_keys(ctx.secrets, ctx.box_secrets)["GEMINI_API_KEY"]
        if not key:
            ctx.note("story", "Draft failed (no key)", headline="Draft failed")
            return notice("/stories", "draft-needed")
        writer = ctx.drafter or GeminiScriptDraft(api_key=key, post=ctx.draft_post or gemini_http_post)
        notes = load_story_notes(ctx.stories)
        try:
            script = writer.draft(
                title=notes["title"],
                characters=draft_character_text(notes, ctx.characters),
                interests=notes["interests"],
                outline=notes["outline"],
                duration_seconds=parse_duration_seconds(notes.get("duration_seconds")),
            )
        except Exception as err:
            ctx.note_failed("story", "Draft", err)
            message = str(getattr(err, "vendor_message", "") or "").strip()
            if message:
                return notice("/stories", "draft-needed", message)
            return notice("/stories", "draft-needed")
        write_story_notes(
            ctx.stories,
            title=notes["title"],
            characters=notes["characters"],
            interests=notes["interests"],
            outline=notes["outline"],
            script=script,
            character_slugs=character_slug_list(notes),
        )
        ctx.note("story", f"Drafted story {notes['title'] or 'untitled'}", headline="Story drafted")
        return notice("/stories", "drafted")

    @app.post("/stories/speak", response_model=None)
    async def speak_story(request: Request) -> RedirectResponse:
        if ctx.stories is None:
            raise HTTPException(status_code=404)
        keys = studio_keys(ctx.secrets, ctx.box_secrets)
        named_voices = load_voices()
        allowed = {voice["id"] for voice in named_voices}
        form = await request.form()
        open_story_pack(ctx.stories, str(form.get("slug") or "").strip())
        chosen = str(form.get("voice_id") or "").strip()
        voice_id = chosen if chosen in allowed else (named_voices[0]["id"] if named_voices else "")
        key = elevenlabs_api_key(keys["ELEVENLABS_API_KEY"])
        if keys["ELEVENLABS_API_KEY"] and not key:
            ctx.note("speak", "Speak failed (key id)", headline="Speak failed")
            return notice("/stories", "speak-key-id")
        if not key or not voice_id:
            ctx.note("speak", "Speak failed (no key)", headline="Speak failed")
            return notice("/stories", "speak-needed")
        notes = load_story_notes(ctx.stories)
        script = notes["script"].strip()
        if not script:
            ctx.note("speak", "Speak failed (no script)", headline="Speak failed")
            return notice("/stories", "speak-needed")
        speaker = ctx.speech or ElevenLabsSpeech(api_key=key, post=ctx.speak_post or http_post)
        try:
            audio = speaker.speak(text=script, voice_id=voice_id)
        except Exception as err:
            ctx.note_failed("speak", "Speak", err)
            message = str(getattr(err, "vendor_message", "") or "").strip()
            if message:
                return notice("/stories", "speak-needed", message)
            return notice("/stories", "speak-needed")
        pack = current_pack(ctx.stories)
        slug = pack.name if pack != ctx.stories else story_slug(notes["title"])
        filename = unique_track_filename(
            slug=slug,
            taken=set(library_paths(ctx.storage)),
            keep=spoken_file_name(ctx.stories),
        )

        class Quiet:
            def tell(self, message: str) -> None:
                return

        stored = add_track(
            audio=audio,
            filename=filename,
            storage=ctx.storage,
            notices=ctx.notices if ctx.notices is not None else Quiet(),
            catalog=ctx.catalog,
        )
        if not stored:
            ctx.note("speak", "Speak failed (full)", headline="Speak failed")
            return notice("/stories", "full")
        if pack != ctx.stories and pack.is_dir():
            for old in pack.iterdir():
                if old.is_file() and old.suffix.lower() == ".mp3" and old.name != filename:
                    old.unlink()
        pack.mkdir(parents=True, exist_ok=True)
        (pack / filename).write_bytes(audio)
        record_spoken_track(pack, filename=filename, library_path=filename)
        ctx.note("speak", f"Spoke story {notes['title'] or filename}", headline="Story spoken")
        return notice("/stories", "spoke")
