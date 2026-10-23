from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from time import sleep as wall_sleep

from romini.composition.catalog import poll_catalog
from romini.composition.nfc import NFC_POLL_SEC, Nfc, poll_nfc
from romini.composition.sim import SimBox
from romini.features.play_by_tag.place_figure import PlayMode, next_assign_mode
from romini.features.power.host import radio_should_sleep
from romini.features.power.quiet import QuietHold
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


def switch_is_open(box: SimBox) -> bool:
    switch = getattr(box, "quiet_switch", None)
    if switch is None:
        return False
    is_open = getattr(switch, "is_open", None)
    if not callable(is_open):
        return False
    return bool(is_open())


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
    hold = QuietHold()
    for _ in ticks:
        was_quiet = hold.quiet
        hold.follow(open_switch=switch_is_open(box), player=box.player)
        box.quiet = hold.quiet
        seen = poll_nfc(box, nfc, previous_uid=previous_uid, absent_ticks=absent_ticks)
        if was_quiet and not hold.quiet:
            hold.resume(
                player=box.player,
                present_uid=seen,
                require_present=box.play_mode is PlayMode.PRESENCE,
            )
            if not box.player.is_playing() and seen is not None:
                box.place(seen)
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
        host_power = getattr(box, "host_power", None)
        if host_power is not None:
            traffic = getattr(box, "traffic", None)
            since = None if traffic is None else traffic.seconds_since(monotonic())
            host_power.apply(
                playing=box.player.is_playing(),
                radio_sleep=radio_should_sleep(seconds_since_request=since),
            )
        sleep(step)
