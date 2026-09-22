from datetime import UTC, datetime, timedelta

from romini.features.play_by_tag.sleep import next_sleep, sleep_is_due


def test_sleep_is_due_only_after_the_deadline() -> None:
    now = datetime(2026, 9, 22, 20, 0, tzinfo=UTC)
    later = now + timedelta(minutes=30)

    assert sleep_is_due(until=None, now=now) is False
    assert sleep_is_due(until=later, now=now) is False
    assert sleep_is_due(until=now, now=now) is True


def test_extend_adds_to_a_future_deadline() -> None:
    now = datetime(2026, 9, 22, 20, 0, tzinfo=UTC)
    until = now + timedelta(minutes=10)

    extended = next_sleep(until=until, now=now, minutes=15, extend=True)
    fresh = next_sleep(until=until, now=now, minutes=30, extend=False)

    assert extended == until + timedelta(minutes=15)
    assert fresh == now + timedelta(minutes=30)
