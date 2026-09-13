import sqlite3
from pathlib import Path


class SqliteSessions:
    def __init__(self, path: Path) -> None:
        self._path = path
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS sessions (uid TEXT PRIMARY KEY, position_sec REAL NOT NULL)")

    def remember(self, uid: str, position_sec: float) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO sessions (uid, position_sec) VALUES (?, ?) "
                "ON CONFLICT(uid) DO UPDATE SET position_sec = excluded.position_sec",
                (uid, position_sec),
            )

    def position_for(self, uid: str) -> float | None:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT position_sec FROM sessions WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return float(row[0])
