import sqlite3
from pathlib import Path


class SqliteCatalog:
    def __init__(self, path: Path) -> None:
        self._path = path
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS catalog (uid TEXT PRIMARY KEY, path TEXT NOT NULL)")

    def replace_tracks(self, tracks: dict[str, str]) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute("DELETE FROM catalog")
            conn.executemany(
                "INSERT INTO catalog (uid, path) VALUES (?, ?)",
                list(tracks.items()),
            )

    def track_for(self, uid: str) -> str | None:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT path FROM catalog WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None
        return str(row[0])
