from datetime import UTC, datetime, timedelta

from romini.features.listening.log import MemoryPlayLog, sync_playback


def test_play_log_opens_when_sound_starts_and_closes_when_it_stops() -> None:
    log = MemoryPlayLog()
    started = datetime(2026, 9, 23, 8, 0, tzinfo=UTC)
    stopped = started + timedelta(minutes=10)
    resumed = stopped + timedelta(minutes=2)

    sync_playback(log, was_playing=False, is_playing=True, at=started)
    sync_playback(log, was_playing=True, is_playing=True, at=started + timedelta(minutes=1))
    sync_playback(log, was_playing=True, is_playing=False, at=stopped)
    sync_playback(log, was_playing=False, is_playing=True, at=resumed)

    intervals = log.intervals()
    assert len(intervals) == 2
    assert intervals[0].started_at == started
    assert intervals[0].ended_at == stopped
    assert intervals[1].started_at == resumed
    assert intervals[1].ended_at is None
