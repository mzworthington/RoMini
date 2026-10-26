from fastapi import Request
from fastapi.responses import HTMLResponse

import romini.composition.dashboard.shared as seams
from romini.composition.dashboard.catalog_view import catalog_board
from romini.composition.dashboard.library_view import library_context
from romini.composition.dashboard.responses import memory_fill
from romini.composition.dashboard.shell_view import (
    audit_rows,
    charge_context,
    device_context,
    disk_context,
    figure_stats,
    filter_context,
    key_context,
    listen_today_label,
    notice_text,
    play_settings,
    sleep_context,
    static_context,
    update_report,
)
from romini.composition.dashboard.studio_view import story_context
from romini.composition.dashboard.templates_env import templates


def render_page(
    request: Request,
    template: str,
    *,
    page: str,
    page_title: str,
    source: object,
    flash: str = "",
) -> HTMLResponse:
    tracks, tags, removed = catalog_board(
        request,
        page=page,
        storage=source.storage,
        assign_catalog=source.assign_catalog,
        covers=source.covers,
        player=source.player,
    )
    library = library_context(page, source.storage, source.stories, tracks, removed)
    shown = library["tracks"]
    now = seams.datetime.now().astimezone()
    host = seams.read_demo_host_facts() if source.demo else seams.read_host_facts()
    update = update_report(source.update_status)
    play_mode, sleep_at = play_settings(source.settings)
    context: dict[str, object] = {
        "notice": notice_text(request, flash),
        "tracks": shown,
        "tags": tags,
        "play_mode": play_mode,
        "host": host,
        "update": update,
        "player_log": _player_log(page, demo=source.demo),
        "memory_fill": memory_fill(host["memory"]),
        "listen_today": listen_today_label(page, source.listening, now),
        "audit_entries": audit_rows(source.audit, page),
        "library_paths": library["library_paths"],
        "library_files": library["library_files"],
    }
    context.update(static_context(page=page, page_title=page_title, demo=source.demo))
    context.update(disk_context(source.storage))
    context.update(story_context(page, source.stories, source.characters))
    context.update(key_context(page, source.secrets, source.box_secrets))
    context.update(filter_context(request))
    context.update(figure_stats(shown, tags))
    context.update(charge_context(source.battery))
    context.update(sleep_context(source.settings, sleep_at, now))
    context.update(device_context(source, page=page, update=update, tracks=shown, tags=tags))
    return templates.TemplateResponse(request, template, context)


def _player_log(page: str, *, demo: bool) -> str:
    if page != "settings" or demo:
        return ""
    return seams.read_player_log()
