from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from time import sleep as wall_sleep

from romini.composition.catalog import poll_catalog
from romini.composition.nfc import NFC_POLL_SEC, Nfc, poll_nfc
from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import next_assign_mode
from romini.features.play_by_tag.sleep import sleep_is_due


def apply_due_sleep(box: SimBox, *, now: datetime) -> None:
    settings = getattr(box, "settings", None)
    if settings is None:
        return
    if not sleep_is_due(until=settings.sleep_until(), now=now):
        return
    if box.player.is_playing():
        box.player.pause()
        box.note("sleep", "Paused for sleep")
    settings.clear_sleep()


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
    idle_sec = 0.0
    absent_ticks = [0]
    for _ in ticks:
        apply_due_sleep(box, now=datetime.now(UTC))
        seen = poll_nfc(box, nfc, previous_uid=previous_uid, absent_ticks=absent_ticks)
        if box.assign_mode:
            if seen is not None and seen != previous_uid:
                idle_sec = 0.0
            else:
                idle_sec += NFC_POLL_SEC
            box.assign_mode = next_assign_mode(assign_mode=True, idle_sec=idle_sec)
        else:
            idle_sec = 0.0
        previous_uid = seen
        previous_mtime = poll_catalog(box, data_dir=data_dir, previous_mtime=previous_mtime)
        sleep(NFC_POLL_SEC)
