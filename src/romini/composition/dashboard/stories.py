import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from romini.composition.dashboard.ctx import DashboardCtx
from romini.composition.dashboard.packs import (
    character_slug_list,
    clear_current,
    current_pack,
    draft_character_text,
    load_story_notes,
    open_story_pack,
    safe_character_slugs,
    spoken_file_name,
    write_story_notes,
)
from romini.composition.dashboard.responses import notice, vendor_detail
from romini.composition.dashboard.routing import mount_routes
from romini.composition.dashboard.speech import speak_story
from romini.composition.dashboard.studio_keys import studio_keys
from romini.composition.story_draft import GeminiScriptDraft, gemini_http_post, parse_duration_seconds


def mount(app: FastAPI, ctx: DashboardCtx) -> None:
    mount_routes(
        app,
        ctx,
        [
            ("/stories", ["GET"], stories_page, False, {"response_model": None}),
            ("/stories/{slug}", ["GET"], story_page, False, {"response_class": HTMLResponse}),
            ("/stories/{slug}/spoken", ["GET"], preview_spoken, False, {}),
            ("/write", ["GET"], write_page, True, {}),
            ("/stories", ["POST"], save_story_notes, False, {"response_model": None}),
            ("/stories/open", ["POST"], open_story, False, {"response_model": None}),
            ("/stories/new", ["POST"], new_story, True, {"response_model": None}),
            ("/stories/delete", ["POST"], delete_story, False, {"response_model": None}),
            ("/stories/draft", ["POST"], draft_story, True, {"response_model": None}),
            ("/stories/speak", ["POST"], speak_story, False, {"response_model": None}),
        ],
    )


def stories_page(ctx: DashboardCtx, request: Request) -> HTMLResponse | RedirectResponse:
    if ctx.stories is None:
        return ctx.page(request, "stories.html", page="stories", page_title="Story Studio")
    pack = current_pack(ctx.stories)
    if pack == ctx.stories:
        return ctx.page(request, "stories.html", page="stories", page_title="Story Studio")
    dest = f"/stories/{pack.name}"
    if request.url.query:
        dest = f"{dest}?{request.url.query}"
    return RedirectResponse(dest, status_code=303)


def story_page(ctx: DashboardCtx, request: Request) -> HTMLResponse:
    slug = str(request.path_params["slug"])
    _open_known_story(ctx, slug)
    return ctx.page(request, "stories.html", page="stories", page_title="Story Studio")


def preview_spoken(ctx: DashboardCtx, request: Request) -> FileResponse:
    slug = str(request.path_params["slug"])
    path = _spoken_file(ctx, slug)
    return FileResponse(path, media_type="audio/mpeg")


def write_page(_ctx: DashboardCtx) -> RedirectResponse:
    return RedirectResponse("/stories", status_code=303)


async def save_story_notes(ctx: DashboardCtx, request: Request) -> RedirectResponse:
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


async def open_story(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    slug = str(form.get("slug") or "").strip()
    open_story_pack(ctx.stories, slug)
    if slug:
        ctx.note("story", f"Opened story {slug}", headline="Story opened")
    return notice("/stories", "story")


def new_story(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    clear_current(ctx.stories)
    return RedirectResponse("/stories", status_code=303)


async def delete_story(ctx: DashboardCtx, request: Request) -> RedirectResponse:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    form = await request.form()
    slug = str(form.get("slug") or "").strip()
    _remove_story(ctx, slug)
    return notice("/stories", "story")


def draft_story(ctx: DashboardCtx) -> RedirectResponse:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    key = studio_keys(ctx.secrets, ctx.box_secrets)["GEMINI_API_KEY"]
    if not key:
        ctx.note("story", "Draft failed (no key)", headline="Draft failed")
        return notice("/stories", "draft-needed")
    return _draft_script(ctx, key)


def _open_known_story(ctx: DashboardCtx, slug: str) -> None:
    if ctx.stories is None:
        raise HTTPException(status_code=404)
    open_story_pack(ctx.stories, slug)
    if current_pack(ctx.stories) != ctx.stories / slug:
        raise HTTPException(status_code=404)


def _spoken_file(ctx: DashboardCtx, slug: str) -> Path:
    _open_known_story(ctx, slug)
    filename = spoken_file_name(ctx.stories)
    if not filename:
        raise HTTPException(status_code=404)
    path = ctx.stories / slug / filename
    if not path.is_file():
        raise HTTPException(status_code=404)
    return path


def _remove_story(ctx: DashboardCtx, slug: str) -> None:
    pack = ctx.stories / slug
    if not _deletable(slug, pack):
        return
    if current_pack(ctx.stories) == pack:
        clear_current(ctx.stories)
    shutil.rmtree(pack)
    ctx.note("story", f"Deleted story {slug}", headline="Story deleted")


def _deletable(slug: str, pack: Path) -> bool:
    if not slug or slug in {".", ".."} or "/" in slug or "\\" in slug:
        return False
    return (pack / "story.yaml").is_file()


def _draft_script(ctx: DashboardCtx, key: str) -> RedirectResponse:
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
        return _draft_failed(ctx, err)
    _save_draft(ctx, notes, script)
    return notice("/stories", "drafted")


def _draft_failed(ctx: DashboardCtx, err: Exception) -> RedirectResponse:
    ctx.note_failed("story", "Draft", err)
    message = vendor_detail(err)
    if message:
        return notice("/stories", "draft-needed", message)
    return notice("/stories", "draft-needed")


def _save_draft(ctx: DashboardCtx, notes: dict[str, str], script: str) -> None:
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
