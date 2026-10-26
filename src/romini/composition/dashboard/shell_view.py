import os
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from romini.composition.dashboard.responses import HOME_NOTICES, format_free_space
from romini.composition.dashboard.studio_keys import (
    DRAFT_MODEL,
    VOICE_MODEL,
    elevenlabs_api_key,
    mask_secret,
    studio_keys,
)
from romini.composition.update import describe_update_center
from romini.features.audit.record import KEEP
from romini.features.listening.today import format_listen_length, listening_today
from romini.features.play_by_tag.now_playing import describe_now_playing
from romini.features.play_by_tag.place_figure import PlayMode
from romini.features.safety.bedtime import bedtime_due, sleep_label


def installed_version() -> str:
    try:
        return version("romini")
    except PackageNotFoundError:
        return "0.0.0"


def static_context(*, page: str, page_title: str, demo: bool) -> dict[str, object]:
    return {
        "page": page,
        "page_title": page_title,
        "draft_model": DRAFT_MODEL,
        "voice_model": VOICE_MODEL,
        "version": installed_version(),
        "presence": PlayMode.PRESENCE.value,
        "tap": PlayMode.TAP.value,
        "demo": demo,
    }


def notice_text(request: object, flash: str) -> str:
    if flash:
        return flash
    detail = request.query_params.get("detail", "").strip()
    if detail:
        return detail
    return HOME_NOTICES.get(request.query_params.get("notice", ""), "")


def filter_context(request: object) -> dict[str, object]:
    query = request.query_params.get("q", "").strip()
    figure_filter = "open" if request.query_params.get("filter") == "open" else "all"
    return {
        "query": query,
        "unassigned": request.query_params.get("unassigned", "") == "1",
        "figure_filter": figure_filter,
        "figure_query": query,
        "focus_uid": request.query_params.get("uid", "").strip(),
        "bind_prompt": request.query_params.get("bind", "") == "1",
    }


def disk_context(storage: object) -> dict[str, object]:
    total = getattr(storage, "total_bytes", None)
    root = getattr(storage, "root", None)
    context = {
        "free_space": format_free_space(storage.free_bytes),
        "library_root": str(root) if root else "",
        "disk_total": "",
        "disk_used": "",
        "disk_fill": 0,
    }
    if isinstance(total, int) and total > 0:
        _fill_disk(context, storage, total)
    return context


def charge_context(battery: object | None) -> dict[str, object]:
    if battery is None:
        return {"charge": None, "pack_volts": None, "pack_flow": None}
    return {
        "charge": battery.percent,
        "pack_volts": getattr(battery, "volts", None),
        "pack_flow": getattr(battery, "flow", None),
    }


def key_context(page: str, secrets: Path | None, box_secrets: Path | None) -> dict[str, object]:
    keys = studio_keys(secrets, box_secrets) if page in {"stories", "characters", "settings"} else {}
    secret = elevenlabs_api_key(keys.get("ELEVENLABS_API_KEY", ""))
    return {
        "elevenlabs_voices": keys.get("ELEVENLABS_VOICE_IDS", ""),
        "gemini_key_set": bool(keys.get("GEMINI_API_KEY")),
        "elevenlabs_key_set": bool(secret),
        "elevenlabs_key_id": bool(keys.get("ELEVENLABS_API_KEY")) and not secret,
        "gemini_key_mask": mask_secret(keys.get("GEMINI_API_KEY", "")),
        "elevenlabs_key_mask": mask_secret(secret),
    }


def play_settings(settings: object | None) -> tuple[str, datetime | None]:
    if settings is None:
        return PlayMode.PRESENCE.value, None
    remembered = settings.play_mode()
    play_mode = remembered.value if remembered is not None else PlayMode.PRESENCE.value
    return play_mode, settings.sleep_at()


def sleep_context(settings: object | None, sleep_at: datetime | None, now: datetime) -> dict[str, object]:
    armed = False
    if sleep_at is not None:
        armed = not bedtime_due(sleep_at, now)
    return {
        "can_sleep": settings is not None,
        "sleep_label": sleep_label(sleep_at, now),
        "sleep_armed": armed,
        "nfc_beep": settings.nfc_beep() if settings is not None else True,
    }


def figure_stats(tracks: list[dict[str, str]], tags: list[dict[str, str]]) -> dict[str, object]:
    bound = {track["uid"] for track in tracks if track["uid"].strip()}
    unbound = [tag for tag in tags if tag["uid"] not in bound]
    active = len(tags) - len(unbound)
    fill = round(100 * active / len(tags)) if tags else 0
    return {"unbound_tags": unbound, "active_figures": active, "figure_fill": fill}


def audit_rows(audit: object | None, page: str) -> list[dict[str, str]]:
    if audit is None or page not in {"figures", "settings"}:
        return []
    return [_audit_row(entry) for entry in audit.recent(limit=KEEP)]


def device_context(
    source: object,
    *,
    page: str,
    update: dict[str, str],
    tracks: list[dict[str, str]],
    tags: list[dict[str, str]],
) -> dict[str, object]:
    context = {}
    context.update(_mixer_context(source.mixer))
    context.update(_player_context(source.player, tracks, tags))
    context.update(_register_context(source.register, page, update))
    context["pad"] = source.pad is not None
    context["can_power"] = source.power is not None
    context["can_update"] = source.updates is not None
    return context


def update_report(update_status: Path | None) -> dict[str, str]:
    channel = os.environ.get("GITHUB_REPO", "mzworthington/RoMini")
    return describe_update_center(update_status, channel=channel)


def listen_today_label(page: str, listening: object | None, now: datetime) -> str:
    if page != "figures" or listening is None:
        return "0m"
    return format_listen_length(listening_today(listening.intervals(), now=now))


def _fill_disk(context: dict[str, object], storage: object, total: int) -> None:
    used = max(total - storage.free_bytes, 0)
    context["disk_total"] = format_free_space(total).removesuffix(" free")
    context["disk_used"] = format_free_space(used).removesuffix(" free")
    context["disk_fill"] = min(100, round(100 * used / total))


def _audit_row(entry: object) -> dict[str, str]:
    headline = entry.headline.strip() or entry.action.replace("-", " ").capitalize()
    return {
        "when": entry.happened_at.strftime("%Y-%m-%d %H:%M"),
        "clock": entry.happened_at.strftime("%H:%M"),
        "when_iso": entry.happened_at.isoformat(),
        "headline": headline,
        "summary": entry.summary,
    }


def _mixer_context(mixer: object | None) -> dict[str, object]:
    if mixer is None:
        return {"mixer": False, "volume_level": 0, "volume_ceiling": 100}
    return {"mixer": True, "volume_level": mixer.level, "volume_ceiling": mixer.ceiling}


def _player_context(
    player: object | None,
    tracks: list[dict[str, str]],
    tags: list[dict[str, str]],
) -> dict[str, object]:
    if player is None:
        return {"has_player": False, "now_playing": None, "playing_uid": ""}
    playing_uid = ""
    if player.is_playing():
        playing_uid = player.playing_uid() or ""
    return {
        "has_player": True,
        "now_playing": describe_now_playing(player, tracks=tracks, tags=tags),
        "playing_uid": playing_uid,
    }


def _register_context(register: object | None, page: str, update: dict[str, str]) -> dict[str, object]:
    assign = bool(register.assign_mode) if register is not None else False
    return {
        "register": register is not None,
        "assign_mode": assign,
        "poll": _should_poll(page, register, assign, update),
    }


def _should_poll(page: str, register: object | None, assign: bool, update: dict[str, str]) -> bool:
    if page == "figures" and register is not None and assign:
        return True
    return page == "settings" and update["label"] == "Checking"
