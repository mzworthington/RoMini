from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class NowPlayingPlayer(Protocol):
    def is_playing(self) -> bool: ...

    def playing_uid(self) -> str | None: ...

    def playing_path(self) -> str | None: ...

    def started_at(self) -> datetime | None: ...

    def stop(self) -> None: ...


@dataclass(frozen=True)
class NowPlaying:
    story: str
    trigger: str
    time: str
    is_playing: bool
    place: str
    length: str = ""
    progress: int = 0
    uid: str = ""
    image: str = ""


def format_place(position_sec: float) -> str:
    total = max(0, int(position_sec))
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"


def format_clock(started_at: datetime | None) -> str:
    if started_at is None:
        return ""
    return started_at.strftime("%H:%M")


def describe_now_playing(
    player: NowPlayingPlayer,
    *,
    tracks: list[dict[str, str]],
    tags: list[dict[str, str]],
) -> NowPlaying | None:
    if not _has_selection(player):
        return None
    uid = player.playing_uid() or ""
    path = player.playing_path() or ""
    matched = _matching_track(tracks, uid, path)
    position = _position(player)
    raw_image = matched.get("image") or ""
    return NowPlaying(
        story=_story_title(matched, path),
        trigger=_trigger_name(tags, uid),
        time=format_clock(player.started_at()),
        is_playing=player.is_playing(),
        place=format_place(position),
        length=matched.get("length") or "",
        progress=_progress(position, int(matched.get("duration_sec") or 0)),
        uid=uid,
        image=raw_image if isinstance(raw_image, str) else "",
    )


def _has_selection(player: NowPlayingPlayer) -> bool:
    if player.is_playing():
        return True
    return bool(player.playing_uid() and player.playing_path())


def _matching_track(tracks: list[dict[str, str]], uid: str, path: str) -> dict[str, str]:
    for track in tracks:
        if track.get("uid") == uid or track.get("path") == path:
            return track
    return {}


def _story_title(matched: dict[str, str], path: str) -> str:
    title = matched.get("title") or ""
    if title:
        return title
    return Path(path).name


def _trigger_name(tags: list[dict[str, str]], uid: str) -> str:
    for tag in tags:
        if tag.get("uid") == uid:
            return tag.get("name") or ""
    return uid


def _position(player: object) -> float:
    read = getattr(player, "position_sec", None)
    if not callable(read):
        return 0.0
    return float(read())


def _progress(position: float, duration: int) -> int:
    if not duration:
        return 0
    return min(100, max(0, round(100 * position / duration)))
