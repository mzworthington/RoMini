RADIO_HOLD_SEC = 30.0


class DashboardTraffic:
    def __init__(self) -> None:
        self.seen_at: float | None = None

    def note(self, now: float) -> None:
        self.seen_at = now

    def seconds_since(self, now: float) -> float | None:
        if self.seen_at is None:
            return None
        return now - self.seen_at


def radio_should_sleep(*, seconds_since_request: float | None) -> bool:
    """The parent dashboard stays reachable on the house LAN, so the radio stays awake."""
    del seconds_since_request
    return False


def cpu_governor(*, playing: bool) -> str:
    if playing:
        return "ondemand"
    return "powersave"
