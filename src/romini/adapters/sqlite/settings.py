import sqlite3
from datetime import datetime
from pathlib import Path

from romini.adapters.sqlite.schema import ensure_schema, open_state
from romini.features.play_by_tag.place_figure import PlayMode


class SqliteSettings:
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

    def remember_play_mode(self, play_mode: PlayMode) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('play_mode', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (play_mode.value,),
        )
        conn.commit()
        self._release(conn)

    def play_mode(self) -> PlayMode | None:
        conn = self._connect()
        row = conn.execute("SELECT value FROM settings WHERE key = 'play_mode'").fetchone()
        self._release(conn)
        if row is None:
            return None
        return PlayMode(row[0])

    def remember_nfc_beep(self, on: bool) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('nfc_beep', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("on" if on else "off",),
        )
        conn.commit()
        self._release(conn)

    def nfc_beep(self) -> bool:
        conn = self._connect()
        row = conn.execute("SELECT value FROM settings WHERE key = 'nfc_beep'").fetchone()
        self._release(conn)
        if row is None:
            return True
        return row[0] != "off"

    def remember_sleep_at(self, deadline: datetime | None) -> None:
        conn = self._connect()
        if deadline is None:
            conn.execute("DELETE FROM settings WHERE key = 'sleep_at'")
        else:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('sleep_at', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (deadline.isoformat(),),
            )
        conn.commit()
        self._release(conn)

    def sleep_at(self) -> datetime | None:
        conn = self._connect()
        row = conn.execute("SELECT value FROM settings WHERE key = 'sleep_at'").fetchone()
        self._release(conn)
        if row is None:
            return None
        return datetime.fromisoformat(row[0])

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        assert self._path is not None
        return open_state(self._path)

    def _release(self, conn: sqlite3.Connection) -> None:
        if self._conn is None:
            conn.close()
