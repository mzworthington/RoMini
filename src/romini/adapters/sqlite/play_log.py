import sqlite3
from datetime import datetime
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.features.listening.today import PlayInterval


class SqlitePlayLog:
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

    def begin(self, at: datetime) -> None:
        conn = self._connect()
        open_row = conn.execute("SELECT id FROM play_log WHERE ended_at IS NULL LIMIT 1").fetchone()
        if open_row is None:
            conn.execute("INSERT INTO play_log (started_at, ended_at) VALUES (?, NULL)", (at.isoformat(),))
            conn.commit()
        self._release(conn)

    def end(self, at: datetime) -> None:
        conn = self._connect()
        conn.execute(
            "UPDATE play_log SET ended_at = ? WHERE id = ("
            "SELECT id FROM play_log WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ")",
            (at.isoformat(),),
        )
        conn.commit()
        self._release(conn)

    def intervals(self) -> list[PlayInterval]:
        conn = self._connect()
        rows = conn.execute("SELECT started_at, ended_at FROM play_log ORDER BY id").fetchall()
        self._release(conn)
        intervals: list[PlayInterval] = []
        for started_at, ended_at in rows:
            intervals.append(
                PlayInterval(
                    started_at=datetime.fromisoformat(started_at),
                    ended_at=datetime.fromisoformat(ended_at) if ended_at else None,
                )
            )
        return intervals

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
