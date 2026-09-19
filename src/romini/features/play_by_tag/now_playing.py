from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol


class NowPlayingPlayer(Protocol):
    def is_playing(self) -> bool: ...

    def playing_uid(self) -> str | None: ...

    def playing_path(self) -> str | None: ...

    def started_at(self) -> datetime | None: ...


@dataclass(frozen=True)
class NowPlaying:
    story: str
    trigger: str
    time: str
    is_playing: bool


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
    if not player.is_playing() and not (player.playing_uid() and player.playing_path()):
        return None
    uid = player.playing_uid() or ""
    path = player.playing_path() or ""
    story = (
        next(
            (track.get("title") or "" for track in tracks if track.get("uid") == uid or track.get("path") == path),
            "",
        )
        or Path(path).name
    )
    trigger = next((tag.get("name") or "" for tag in tags if tag.get("uid") == uid), "") or uid
    return NowPlaying(
        story=story,
        trigger=trigger,
        time=format_clock(player.started_at()),
        is_playing=player.is_playing(),
    )
