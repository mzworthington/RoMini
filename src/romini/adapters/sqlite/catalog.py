import sqlite3
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state


class SqliteCatalog:
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

    def replace_tracks(self, tracks: dict[str, str]) -> None:
        conn = self._connect()
        conn.execute("DELETE FROM catalog")
        conn.executemany(
            "INSERT INTO catalog (uid, path) VALUES (?, ?)",
            list(tracks.items()),
        )
        conn.commit()
        self._release(conn)

    def track_for(self, uid: str) -> str | None:
        conn = self._connect()
        row = conn.execute("SELECT path FROM catalog WHERE uid = ?", (uid,)).fetchone()
        self._release(conn)
        if row is None:
            return None
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
