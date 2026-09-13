import sqlite3
from pathlib import Path

from romini.features.play_by_tag.place_figure import PlayMode


class SqliteSettings:
    def __init__(self, path: Path) -> None:
        self._path = path
        with sqlite3.connect(path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")

    def remember_play_mode(self, play_mode: PlayMode) -> None:
        with sqlite3.connect(self._path) as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('play_mode', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (play_mode.value,),
            )

    def play_mode(self) -> PlayMode | None:
        with sqlite3.connect(self._path) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'play_mode'").fetchone()
        if row is None:
            return None
        return PlayMode(row[0])
