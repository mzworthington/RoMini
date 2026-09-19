from typing import Protocol


class Battery(Protocol):
    percent: int | None


def percent_from_pack_volts(volts: float) -> int:
    raw = (volts - 3.0) / 1.2 * 100
    return max(0, min(100, round(raw)))
