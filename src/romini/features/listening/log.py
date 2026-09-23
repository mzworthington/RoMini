from datetime import datetime
from typing import Protocol

from romini.features.listening.today import PlayInterval


class PlayLog(Protocol):
    def begin(self, at: datetime) -> None: ...

    def end(self, at: datetime) -> None: ...

    def intervals(self) -> list[PlayInterval]: ...


class MemoryPlayLog:
    def __init__(self) -> None:
        self._intervals: list[PlayInterval] = []

    def begin(self, at: datetime) -> None:
        if self._intervals and self._intervals[-1].ended_at is None:
            return
        self._intervals.append(PlayInterval(started_at=at, ended_at=None))

    def end(self, at: datetime) -> None:
        if not self._intervals or self._intervals[-1].ended_at is not None:
            return
        open_interval = self._intervals[-1]
        self._intervals[-1] = PlayInterval(started_at=open_interval.started_at, ended_at=at)

    def intervals(self) -> list[PlayInterval]:
        return list(self._intervals)


def sync_playback(log: PlayLog, *, was_playing: bool, is_playing: bool, at: datetime) -> None:
    if was_playing == is_playing:
        return
    if is_playing:
        log.begin(at)
        return
    log.end(at)
