from pathlib import Path

from romini.adapters.sqlite.sessions import SqliteSessions


def test_sqlite_sessions_remember_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "romini.db"

    SqliteSessions(path).remember("04AABBCC", 14.5)

    assert SqliteSessions(path).position_for("04AABBCC") == 14.5
