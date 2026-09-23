import threading
from datetime import UTC, datetime
from pathlib import Path

from romini.adapters.sqlite.audit import SqliteAudit
from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.features.audit.record import record_event


def test_sqlite_audit_lists_newest_first(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    log = SqliteAudit(conn)
    times = iter(
        [
            datetime(2026, 9, 19, 21, 0, tzinfo=UTC),
            datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
        ]
    )
    record_event(log, action="upload", summary="Stored frog.mp3", clock=lambda: next(times))
    record_event(log, action="play", summary="Played The Frog Prince", clock=lambda: next(times))

    recent = log.recent()

    assert [entry.summary for entry in recent] == ["Played The Frog Prince", "Stored frog.mp3"]
    assert recent[0].action == "play"
    assert recent[0].happened_at == datetime(2026, 9, 19, 21, 1, tzinfo=UTC)


def test_sqlite_audit_keeps_the_headline_apart_from_the_description(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    log = SqliteAudit(conn)

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


def test_sqlite_audit_skips_rows_with_blank_happened_at(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    log = SqliteAudit(conn)
    conn.execute(
        "INSERT INTO audit_log (happened_at, action, summary) VALUES (?, ?, ?)",
        ("", "play", "corrupt blank timestamp"),
    )
    conn.commit()
    record_event(
        log,
        action="play",
        summary="Played The Frog Prince",
        clock=lambda: datetime(2026, 9, 19, 21, 1, tzinfo=UTC),
    )

    recent = log.recent()

    assert [entry.summary for entry in recent] == ["Played The Frog Prince"]


def test_shared_audit_connection_survives_concurrent_reads_and_writes(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    log = SqliteAudit(conn)
    errors: list[BaseException] = []

    def worker(worker_id: int) -> None:
        try:
            for n in range(30):
                record_event(
                    log,
                    action="play",
                    summary=f"{worker_id}-{n}",
                    clock=lambda: datetime.now(UTC),
                )
                log.recent()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert log.recent()
