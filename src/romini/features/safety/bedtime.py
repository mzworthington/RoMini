import math
from datetime import datetime, timedelta
from typing import Protocol


class Halt(Protocol):
    def poweroff(self) -> None: ...


SLEEP_MINUTES = 30


def arm_bedtime(now: datetime, *, minutes: int = SLEEP_MINUTES) -> datetime:
    return now + timedelta(minutes=minutes)


def bedtime_due(deadline: datetime | None, now: datetime) -> bool:
    return deadline is not None and now >= deadline


def sleep_label(deadline: datetime | None, now: datetime) -> str:
    if not bedtime_due(deadline, now) and deadline is not None and now < deadline:
        minutes = max(1, math.ceil((deadline - now).total_seconds() / 60))
        return f"Sleeping in {minutes}m"
    return "Sleep in 30m"


def release_bedtime(*, deadline: datetime | None, now: datetime, halt: Halt) -> datetime | None:
    if not bedtime_due(deadline, now):
        return deadline
    halt.poweroff()
    return None
