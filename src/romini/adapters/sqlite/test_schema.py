from datetime import UTC, datetime
from pathlib import Path

from romini.adapters.sqlite.catalog import SqliteCatalog
from romini.adapters.sqlite.mixer import SqliteMixer
from romini.adapters.sqlite.schema import SCHEMA_VERSION, ensure_schema, open_state
from romini.adapters.sqlite.sessions import SqliteSessions
from romini.adapters.sqlite.settings import SqliteSettings
from romini.features.play_by_tag.place_figure import PlayMode


def test_ensure_schema_sets_version_and_creates_tables(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)

    version = conn.execute("SELECT version FROM schema_version WHERE id = 1").fetchone()
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    assert version == (SCHEMA_VERSION,)
    assert {"sessions", "mixer", "settings", "catalog", "audit_log"}.issubset(tables)


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


def test_nfc_beep_defaults_on_and_can_be_turned_off(tmp_path: Path) -> None:
    settings = SqliteSettings(tmp_path / "state.sqlite")

    assert settings.nfc_beep() is True
    settings.remember_nfc_beep(False)

    assert SqliteSettings(tmp_path / "state.sqlite").nfc_beep() is False


def test_sleep_deadline_is_remembered_until_cleared(tmp_path: Path) -> None:
    deadline = datetime(2026, 9, 23, 20, 30, tzinfo=UTC)
    settings = SqliteSettings(tmp_path / "state.sqlite")

    assert settings.sleep_at() is None
    settings.remember_sleep_at(deadline)

    assert SqliteSettings(tmp_path / "state.sqlite").sleep_at() == deadline
    settings.remember_sleep_at(None)
    assert settings.sleep_at() is None


def test_sqlite_catalog_accepts_a_shared_connection(tmp_path: Path) -> None:
    conn = open_state(tmp_path / "state.sqlite")
    ensure_schema(conn)
    SqliteCatalog(conn).replace_tracks({"04AABBCC": "/frog.mp3"})

    assert SqliteCatalog(conn).track_for("04AABBCC") == "/frog.mp3"
