from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from time import sleep as wall_sleep

from romini.composition.catalog import poll_catalog
from romini.composition.nfc import NFC_POLL_SEC, Nfc, poll_nfc
from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import next_assign_mode
from romini.features.power.host import radio_should_sleep
from romini.features.safety.bedtime import release_bedtime

SHELF_HALT_SEC = 600.0


def release_armed_bedtime(box: SimBox, *, now: datetime | None = None) -> None:
    settings = getattr(box, "settings", None)
    if settings is None:
        return
    deadline = settings.sleep_at()
    if deadline is None:
        return
    left = release_bedtime(deadline=deadline, now=now or datetime.now(UTC), halt=box.halt)
    if left is None:
        settings.remember_sleep_at(None)


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
    shelf_idle = 0.0
    absent_ticks = [0]
    for _ in ticks:
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
        release_armed_bedtime(box)
        step = NFC_POLL_SEC
        if seen is None and not box.assign_mode and not box.player.is_playing():
            shelf_idle += step
            if shelf_idle >= SHELF_HALT_SEC:
                lamp_off = getattr(box.led, "off", None)
                if callable(lamp_off):
                    lamp_off()
                box.halt.poweroff()
        else:
            shelf_idle = 0.0
        host_power = getattr(box, "host_power", None)
        if host_power is not None:
            traffic = getattr(box, "traffic", None)
            since = None if traffic is None else traffic.seconds_since(monotonic())
            host_power.apply(
                playing=box.player.is_playing(),
                radio_sleep=radio_should_sleep(seconds_since_request=since),
            )
        sleep(step)
