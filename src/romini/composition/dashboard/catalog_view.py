from pathlib import Path
from urllib.parse import unquote

import yaml

from romini.composition.dashboard.covers import (
    figure_cover_key,
    figure_cover_url,
    locate_track_cover,
    resolve_track_image,
)
from romini.composition.dashboard.media import audio_facts, hidden_track_paths, public_https_url, stored_size
from romini.composition.dashboard.responses import format_tag_uid
from romini.features.library.track_facts import TrackFacts, format_size


def catalog_board(
    request: object,
    *,
    page: str,
    storage: object,
    assign_catalog: object | None,
    covers: Path | None,
    player: object | None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], set[str]]:
    if assign_catalog is None or page in {"stories", "characters"}:
        return [], [], set()
    data = _document(assign_catalog)
    removed = _removed(data, request)
    tags = _tags(data, covers)
    tracks = _tracks(
        data,
        removed=removed,
        storage=storage,
        covers=covers,
        playing=_playing_path(player),
        measure=page in {"library", "figures"},
    )
    return tracks, tags, removed


def _document(assign_catalog: object) -> dict:
    data = yaml.safe_load(assign_catalog.read_text()) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _removed(data: dict, request: object) -> set[str]:
    listed = {str(item) for item in list(data.get("removed") or []) if str(item).strip()}
    return listed | hidden_track_paths(request)


def _tags(data: dict, covers: Path | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for tag in data.get("tags") or []:
        row = _tag_row(tag, covers)
        if row is not None:
            rows.append(row)
    return rows


def _tag_row(tag: dict, covers: Path | None) -> dict[str, str] | None:
    uid = str(tag.get("uid") or "")
    if not uid.strip():
        return None
    return {
        "uid": uid,
        "name": unquote(str(tag.get("name") or "")),
        "uid_label": format_tag_uid(uid),
        "image": _figure_image(uid, covers),
    }


def _figure_image(uid: str, covers: Path | None) -> str:
    key = figure_cover_key(uid)
    if key and locate_track_cover(covers, key):
        return figure_cover_url(uid)
    return ""


def _playing_path(player: object | None) -> str:
    if player is None:
        return ""
    current = getattr(player, "playing_path", None)
    if not callable(current):
        return ""
    return current() or ""


def _tracks(
    data: dict,
    *,
    removed: set[str],
    storage: object,
    covers: Path | None,
    playing: str,
    measure: bool,
) -> list[dict[str, str]]:
    names = {tag["uid"]: tag["name"] for tag in _tags(data, covers)}
    rows: list[dict[str, str]] = []
    for track in data.get("tracks") or []:
        row = _track_row(
            track,
            names=names,
            removed=removed,
            storage=storage,
            covers=covers,
            playing=playing,
            measure=measure,
        )
        if row is not None:
            rows.append(row)
    return rows


def _track_row(
    track: dict,
    *,
    names: dict[str, str],
    removed: set[str],
    storage: object,
    covers: Path | None,
    playing: str,
    measure: bool,
) -> dict[str, str] | None:
    uid = str(track.get("uid") or "")
    title = str(track.get("title") or "")
    path = str(track.get("path") or "")
    if not _show_track(uid, title, path, removed):
        return None
    facts = _playing_facts(storage, path, playing)
    return _track_fields(track, uid, title, path, names, facts, measure, storage, covers)


def _show_track(uid: str, title: str, path: str, removed: set[str]) -> bool:
    if path in removed:
        return False
    return bool(uid.strip() or title.strip() or path.strip())


def _playing_facts(storage: object, path: str, playing: str) -> TrackFacts | None:
    if not path or path != playing:
        return None
    return audio_facts(storage, path)


def _track_fields(
    track: dict,
    uid: str,
    title: str,
    path: str,
    names: dict[str, str],
    facts: TrackFacts | None,
    measure: bool,
    storage: object,
    covers: Path | None,
) -> dict[str, str]:
    size_bytes = _measured_size(facts, measure, storage, path)
    return {
        "uid": uid,
        "title": title,
        "artist": _artist(track),
        "path": path,
        "suffix": Path(path).suffix.lower().lstrip(".").upper(),
        "figure": names.get(uid) or uid,
        "length": _fact_text(facts, "length"),
        "size": _size_label(facts, size_bytes),
        "duration_sec": _fact_text(facts, "duration_sec"),
        "image": resolve_track_image(track, covers=covers, storage=storage),
        "media": public_https_url(storage, path),
    }


def _fact_text(facts: TrackFacts | None, name: str) -> str:
    if facts is None:
        return ""
    return str(getattr(facts, name))


def _artist(track: dict) -> str:
    artist = track.get("artist")
    if artist is None:
        return ""
    return str(artist).strip()


def _measured_size(facts: TrackFacts | None, measure: bool, storage: object, path: str) -> int | None:
    if facts is not None or not measure:
        return None
    return stored_size(storage, path)


def _size_label(facts: TrackFacts | None, size_bytes: int | None) -> str:
    if facts is not None:
        return facts.size
    if size_bytes is None:
        return ""
    return format_size(size_bytes)
