from pathlib import Path

from romini.adapters.sqlite.catalog import SqliteCatalog


def test_sqlite_catalog_unmaps_uid_removed_from_import(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite"
    store = SqliteCatalog(path)
    store.replace_tracks({"04AABBCC": "/var/lib/romini/library/stories/frog-prince.mp3"})

    store.replace_tracks({})

    assert store.track_for("04AABBCC") is None
