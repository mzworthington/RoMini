from datetime import UTC, datetime

from romini.features.audit.memory import MemoryAuditLog
from romini.features.audit.record import record_event


def test_record_event_lists_newest_first() -> None:
    log = MemoryAuditLog()
    times = iter(
        [
            datetime(2026, 9, 19, 21, 0, tzinfo=UTC),
            datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
        ]
    )

    record_event(log, action="upload", summary="frog.mp3", clock=lambda: next(times))
    record_event(log, action="play", summary="The Frog Prince", clock=lambda: next(times))

    recent = log.recent()

    assert [entry.summary for entry in recent] == ["The Frog Prince", "frog.mp3"]
    assert recent[0].action == "play"
    assert recent[0].happened_at == datetime(2026, 9, 19, 21, 1, tzinfo=UTC)


def test_record_event_keeps_the_headline_apart_from_the_description() -> None:
    log = MemoryAuditLog()

    record_event(
        log,
        action="place",
        headline="The Gruffalo placed",
        summary="Story started from the saved bookmark.",
        clock=lambda: datetime(2026, 9, 19, 14, 22, tzinfo=UTC),
    )

    entry = log.recent()[0]
    assert entry.headline == "The Gruffalo placed"
    assert entry.summary == "Story started from the saved bookmark."


def test_memory_audit_keeps_the_last_thousand_events() -> None:
    log = MemoryAuditLog()
    for index in range(1001):
        record_event(
            log,
            action="play",
            summary=f"e{index}",
            clock=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        )

    recent = log.recent(limit=10000)

    assert len(recent) == 1000
    assert recent[0].summary == "e1000"
    assert recent[-1].summary == "e1"
