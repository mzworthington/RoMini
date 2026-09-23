from datetime import UTC, datetime, timedelta

from romini.fakes import FakeHalt
from romini.features.safety.bedtime import arm_bedtime, bedtime_due, release_bedtime


def test_bedtime_is_due_thirty_minutes_after_it_is_armed() -> None:
    now = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)

    deadline = arm_bedtime(now)

    assert deadline == now + timedelta(minutes=30)
    assert bedtime_due(deadline, now + timedelta(minutes=29)) is False
    assert bedtime_due(deadline, deadline) is True


def test_a_due_bedtime_powers_the_box_down() -> None:
    now = datetime(2026, 9, 23, 20, 0, tzinfo=UTC)
    deadline = arm_bedtime(now)
    halt = FakeHalt()

    waiting = release_bedtime(deadline=deadline, now=now, halt=halt)
    finished = release_bedtime(deadline=deadline, now=deadline, halt=halt)

    assert waiting == deadline
    assert halt.poweroffs == 1
    assert finished is None
