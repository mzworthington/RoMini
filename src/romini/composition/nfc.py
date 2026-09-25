from collections.abc import Iterable
from typing import Protocol

from romini.composition.sim import SimBox

NFC_POLL_SEC = 0.25
NFC_ABSENT_TICKS = 3


class Nfc(Protocol):
    def read_uid(self) -> str | None: ...


class FakeNfc:
    def __init__(self, uid: str | None = None) -> None:
        self._uid = uid

    def read_uid(self) -> str | None:
        return self._uid

    def clear(self) -> None:
        self._uid = None


def poll_nfc(
    box: SimBox,
    nfc: Nfc,
    *,
    previous_uid: str | None = None,
    absent_ticks: list[int] | None = None,
) -> str | None:
    uid = nfc.read_uid()
    misses = absent_ticks if absent_ticks is not None else [0]
    if uid is not None:
        if uid != previous_uid:
            box.place(uid)
        misses[0] = 0
        return uid
    if previous_uid is None:
        misses[0] = 0
        return None
    misses[0] += 1
    if misses[0] >= NFC_ABSENT_TICKS:
        box.lift(previous_uid, elapsed_sec=2.1, position_sec=0.0)
        misses[0] = 0
        return None
    return previous_uid


def run_nfc_ticks(box: SimBox, nfc: Nfc, ticks: Iterable[object]) -> None:
    previous_uid: str | None = None
    absent_ticks = [0]
    for _ in ticks:
        previous_uid = poll_nfc(box, nfc, previous_uid=previous_uid, absent_ticks=absent_ticks)
