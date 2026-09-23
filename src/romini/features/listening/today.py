from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PlayInterval:
    started_at: datetime
    ended_at: datetime | None


def listening_today(intervals: list[PlayInterval], *, now: datetime) -> timedelta:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    played = timedelta()
    for interval in intervals:
        end = interval.ended_at if interval.ended_at is not None else now
        start = max(interval.started_at, day_start)
        stop = min(end, day_end, now)
        if stop > start:
            played += stop - start
    return played


def format_listen_length(played: timedelta) -> str:
    minutes = int(played.total_seconds() // 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"
