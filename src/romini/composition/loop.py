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


def _advance_assign(box: SimBox, seen: str | None, previous_uid: str | None, idle_sec: float) -> float:
    if not box.assign_mode:
        return 0.0
    if seen is None or seen == previous_uid:
        idle_sec += NFC_POLL_SEC
    else:
        idle_sec = 0.0
    box.assign_mode = next_assign_mode(assign_mode=True, idle_sec=idle_sec)
    return idle_sec


def _tick_host(box: SimBox) -> None:
    host_power = getattr(box, "host_power", None)
    if host_power is None:
        return
    traffic = getattr(box, "traffic", None)
    since = None if traffic is None else traffic.seconds_since(monotonic())
    host_power.apply(
        playing=box.player.is_playing(),
        radio_sleep=radio_should_sleep(seconds_since_request=since),
    )


def _tick_dashboard(box: SimBox) -> None:
    dashboard = getattr(box, "dashboard", None)
    ensure_serving = getattr(dashboard, "ensure_serving", None)
    if callable(ensure_serving):
        ensure_serving(now=monotonic())


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
        seen = poll_nfc(box, nfc, previous_uid=previous_uid, absent_ticks=absent_ticks)
        idle_sec = _advance_assign(box, seen, previous_uid, idle_sec)
        previous_uid = seen
        previous_mtime = poll_catalog(box, data_dir=data_dir, previous_mtime=previous_mtime)
        release_armed_bedtime(box)
        _tick_host(box)
        _tick_dashboard(box)
        sleep(NFC_POLL_SEC)
