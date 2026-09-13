from typing import Protocol

from romini.composition.sim import SimBox


class Nfc(Protocol):
    def read_uid(self) -> str | None: ...


class FakeNfc:
    def __init__(self, uid: str | None = None) -> None:
        self._uid = uid

    def read_uid(self) -> str | None:
        return self._uid

    def clear(self) -> None:
        self._uid = None


def poll_nfc(box: SimBox, nfc: Nfc, *, previous_uid: str | None = None) -> str | None:
    uid = nfc.read_uid()
    if uid is not None and uid != previous_uid:
        box.place(uid)
    if uid is None and previous_uid is not None:
        box.lift(previous_uid, elapsed_sec=2.1, position_sec=0.0)
    return uid
