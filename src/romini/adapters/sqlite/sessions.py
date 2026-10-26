import sqlite3
from pathlib import Path

from romini.adapters.sqlite.store import SqliteStore


class SqliteSessions(SqliteStore):
    def __init__(self, source: Path | sqlite3.Connection) -> None:
        super().__init__(source)

    def remember(self, uid: str, position_sec: float) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO sessions (uid, position_sec) VALUES (?, ?) "
            "ON CONFLICT(uid) DO UPDATE SET position_sec = excluded.position_sec",
            (uid, position_sec),
        )
        conn.commit()
        self._release(conn)

    def position_for(self, uid: str) -> float | None:
        conn = self._connect()
        row = conn.execute("SELECT position_sec FROM sessions WHERE uid = ?", (uid,)).fetchone()
        self._release(conn)
        if row is None:
            return None
        return float(row[0])
