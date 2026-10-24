import io
import zipfile
from pathlib import Path

import pytest
import yaml

from romini.features.library.backup import restore_backup, write_backup


def test_backup_archive_keeps_story_notes_and_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("tracks: []\n")
    story = tmp_path / "stories" / "frog" / "story.yaml"
    story.parent.mkdir(parents=True)
    story.write_text("title: Frog\n")
    archive = io.BytesIO()

    write_backup(archive, catalog=catalog, stories=tmp_path / "stories", characters=None, library=None)

    archive.seek(0)
    with zipfile.ZipFile(archive) as saved:
        assert set(saved.namelist()) == {"catalog.yaml", "stories/frog/story.yaml"}
        assert saved.read("stories/frog/story.yaml") == b"title: Frog\n"
        assert saved.read("catalog.yaml") == b"tracks: []\n"


def test_backup_archive_keeps_characters_and_library_audio(tmp_path: Path) -> None:
    character = tmp_path / "characters" / "romy" / "character.yaml"
    character.parent.mkdir(parents=True)
    character.write_text("name: Romy\n")
    track = tmp_path / "library" / "frog.mp3"
    track.parent.mkdir()
    track.write_bytes(b"audio")
    archive = io.BytesIO()

    write_backup(
        archive,
        catalog=None,
        stories=None,
        characters=tmp_path / "characters",
        library=tmp_path / "library",
    )

    archive.seek(0)
    with zipfile.ZipFile(archive) as saved:
        assert set(saved.namelist()) == {"characters/romy/character.yaml", "library/frog.mp3"}
        assert saved.read("library/frog.mp3") == b"audio"


def test_backup_records_library_audio_the_catalog_left_out(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("tracks:\n- uid: 6cde55fa\n  path: romys-birthday-party.mp3\n  title: romys birthday party\n")
    folder = tmp_path / "library" / "library"
    folder.mkdir(parents=True)
    (folder / "romys-birthday-party.mp3").write_bytes(b"party")
    (folder / "little-drummer-girl.mp3").write_bytes(b"drum")
    archive = io.BytesIO()

    write_backup(archive, catalog=catalog, stories=None, characters=None, library=tmp_path / "library")

    archive.seek(0)
    with zipfile.ZipFile(archive) as saved:
        recorded = yaml.safe_load(saved.read("catalog.yaml"))
    paths = {row["path"] for row in recorded["tracks"]}
    assert paths == {"library/romys-birthday-party.mp3", "library/little-drummer-girl.mp3"}
    assert {row["path"] for row in yaml.safe_load(catalog.read_text())["tracks"]} == paths


def test_restore_puts_stories_and_catalog_back(tmp_path: Path) -> None:
    source = tmp_path / "source"
    catalog = source / "catalog.yaml"
    catalog.parent.mkdir()
    catalog.write_text("tracks:\n  - uid: aa\n    path: frog.mp3\n")
    story = source / "stories" / "frog" / "story.yaml"
    story.parent.mkdir(parents=True)
    story.write_text("title: Frog\n")
    archive = io.BytesIO()
    write_backup(archive, catalog=catalog, stories=source / "stories", characters=None, library=None)

    restored = tmp_path / "restored"
    archive.seek(0)
    restore_backup(
        archive,
        catalog=restored / "catalog.yaml",
        stories=restored / "stories",
        characters=None,
        library=None,
    )

    assert (restored / "catalog.yaml").read_text() == catalog.read_text()
    assert (restored / "stories" / "frog" / "story.yaml").read_text() == "title: Frog\n"


def test_restore_refuses_a_path_that_leaves_the_data_folders(tmp_path: Path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as saved:
        saved.writestr("stories/../../outside.txt", "nope")
    archive.seek(0)
    stories = tmp_path / "stories"
    stories.mkdir()

    with pytest.raises(ValueError):
        restore_backup(
            archive,
            catalog=tmp_path / "catalog.yaml",
            stories=stories,
            characters=None,
            library=None,
        )

    assert list(stories.rglob("*")) == []
    assert not (tmp_path / "outside.txt").exists()


def test_restore_records_library_audio_the_catalog_left_out(tmp_path: Path) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as saved:
        saved.writestr(
            "catalog.yaml",
            "tracks:\n- uid: 6cde55fa\n  path: romys-birthday-party.mp3\n  title: romys birthday party\n",
        )
        saved.writestr("library/library/romys-birthday-party.mp3", b"party")
        saved.writestr("library/library/little-drummer-girl.mp3", b"drum")
    archive.seek(0)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("tracks: []\n")

    restore_backup(
        archive,
        catalog=catalog,
        stories=None,
        characters=None,
        library=tmp_path / "library",
    )

    paths = {row["path"] for row in yaml.safe_load(catalog.read_text())["tracks"]}
    assert paths == {"library/romys-birthday-party.mp3", "library/little-drummer-girl.mp3"}
    linked = next(
        row for row in yaml.safe_load(catalog.read_text())["tracks"] if row["path"].endswith("romys-birthday-party.mp3")
    )
    assert linked["uid"] == "6cde55fa"
