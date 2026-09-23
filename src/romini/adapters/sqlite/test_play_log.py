from datetime import UTC, datetime, timedelta
from pathlib import Path

from romini.adapters.sqlite.play_log import SqlitePlayLog
from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.features.listening.log import sync_playback


def test_sqlite_play_log_keeps_closed_and_open_intervals(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    log = SqlitePlayLog(conn)
    started = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)
    stopped = started + timedelta(minutes=35)
    resumed = stopped + timedelta(minutes=5)

    sync_playback(log, was_playing=False, is_playing=True, at=started)
    sync_playback(log, was_playing=True, is_playing=False, at=stopped)
    sync_playback(log, was_playing=False, is_playing=True, at=resumed)

    again = SqlitePlayLog(conn)
    intervals = again.intervals()
    assert intervals[0].started_at == started
    assert intervals[0].ended_at == stopped
    assert intervals[1].started_at == resumed
    assert intervals[1].ended_at is None
