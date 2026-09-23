from datetime import datetime, timedelta, timezone

from romini.features.listening.today import PlayInterval, format_listen_length, listening_today


def test_listening_today_counts_only_today_including_what_is_still_playing() -> None:
    zone = timezone(timedelta(hours=1))
    now = datetime(2026, 9, 23, 8, 6, tzinfo=zone)
    intervals = [
        PlayInterval(
            started_at=datetime(2026, 9, 22, 10, 0, tzinfo=zone),
            ended_at=datetime(2026, 9, 22, 11, 0, tzinfo=zone),
        ),
        PlayInterval(
            started_at=datetime(2026, 9, 22, 23, 30, tzinfo=zone),
            ended_at=datetime(2026, 9, 23, 0, 20, tzinfo=zone),
        ),
        PlayInterval(
            started_at=datetime(2026, 9, 23, 7, 0, tzinfo=zone),
            ended_at=datetime(2026, 9, 23, 8, 0, tzinfo=zone),
        ),
        PlayInterval(started_at=datetime(2026, 9, 23, 8, 0, tzinfo=zone), ended_at=None),
    ]

    played = listening_today(intervals, now=now)

    assert played == timedelta(minutes=86)
    assert format_listen_length(played) == "1h 26m"
