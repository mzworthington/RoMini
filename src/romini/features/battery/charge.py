from typing import Protocol


class Battery(Protocol):
    percent: int | None


def flow_from_current_ma(current_ma: float) -> str:
    if current_ma > 0:
        return "charging"
    if current_ma < 0:
        return "discharging"
    return "steady"


def percent_from_pack_volts(volts: float) -> int:
    raw = (volts - 3.0) / 1.2 * 100
    return max(0, min(100, round(raw)))
