import sqlite3
from pathlib import Path

from romini.adapters.sqlite.store import SqliteStore


class SqliteCatalog(SqliteStore):
    def __init__(self, source: Path | sqlite3.Connection) -> None:
        super().__init__(source)

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
