from collections.abc import Callable, Iterable
from pathlib import Path
from time import sleep as wall_sleep

from romini.composition.catalog import poll_catalog
from romini.composition.nfc import NFC_POLL_SEC, Nfc, poll_nfc
from romini.composition.sim import SimBox


def run_core_ticks(
    box: SimBox,
    nfc: Nfc,
    *,
    data_dir: Path,
    ticks: Iterable[object],
    sleep: Callable[[float], None] = wall_sleep,
) -> None:
    previous_uid: str | None = None
    previous_mtime: float | None = None
    for _ in ticks:
        previous_uid = poll_nfc(box, nfc, previous_uid=previous_uid)
        previous_mtime = poll_catalog(box, data_dir=data_dir, previous_mtime=previous_mtime)
        sleep(NFC_POLL_SEC)
