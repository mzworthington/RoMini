from pathlib import Path

from romini.composition.sqlite_catalog import SqliteCatalog
from romini.composition.sqlite_mixer import SqliteMixer
from romini.composition.sqlite_schema import SCHEMA_VERSION, ensure_schema, open_state
from romini.composition.sqlite_sessions import SqliteSessions
from romini.composition.sqlite_settings import SqliteSettings
from romini.features.play_by_tag.place_figure import PlayMode


def test_ensure_schema_sets_version_and_creates_tables(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert version == (SCHEMA_VERSION,)
    assert {"sessions", "mixer", "settings", "catalog"}.issubset(tables)


def test_sqlite_sessions_accept_a_shared_connection(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)

    SqliteSessions(conn).remember("04AABBCC", 14.5)

    assert SqliteSessions(conn).position_for("04AABBCC") == 14.5


def test_sqlite_mixer_accepts_a_shared_connection(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    mixer = SqliteMixer(conn)
    mixer.set_level(7)

    assert SqliteMixer(conn).level == 7


def test_sqlite_settings_accept_a_shared_connection(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    SqliteSettings(conn).remember_play_mode(PlayMode.TAP)

    assert SqliteSettings(conn).play_mode() is PlayMode.TAP


def test_sqlite_catalog_accepts_a_shared_connection(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    SqliteCatalog(conn).replace_tracks({"04AABBCC": "/frog.mp3"})

    assert SqliteCatalog(conn).track_for("04AABBCC") == "/frog.mp3"
