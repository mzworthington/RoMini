from datetime import datetime, timedelta


def sleep_is_due(*, until: datetime | None, now: datetime) -> bool:
    return until is not None and now >= until


def next_sleep(*, until: datetime | None, now: datetime, minutes: int, extend: bool) -> datetime:
    if extend and until is not None and until > now:
        return until + timedelta(minutes=minutes)
    return now + timedelta(minutes=minutes)
