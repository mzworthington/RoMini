import sqlite3
from pathlib import Path

from romini.composition.sqlite_schema import ensure_schema, open_state


class SqliteSessions:
    def __init__(self, source: Path | sqlite3.Connection) -> None:
        if isinstance(source, sqlite3.Connection):
            self._conn = source
            self._path: Path | None = None
        else:
            self._conn = None
            self._path = source
            conn = open_state(source)
            ensure_schema(conn)
            conn.close()

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

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
