import pytest
import yaml

from romini.features.library.import_catalog import import_catalog, include_library_tracks


def test_catalog_maps_tag_to_existing_track() -> None:
    catalog = """
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
"""
    library = import_catalog(
        catalog,
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )

    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_duplicate_uid_is_rejected() -> None:
    catalog = """
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
  - uid: "04aabbccddeeff"
    path: "stories/other.mp3"
    title: "Other"
"""

    with pytest.raises(ValueError):
        import_catalog(
            catalog,
            library_root="/var/lib/romini/library",
            audio_exists=lambda path: True,
        )


def test_catalog_skips_missing_audio_and_keeps_other_tags() -> None:
    catalog = """
tracks:
  - uid: "04aabbccddeeff"
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
  - uid: "04deadbeef0001"
    path: "stories/missing.mp3"
    title: "Missing"
"""
    library = import_catalog(
        catalog,
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )

    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"
    assert library.track_for("04deadbeef0001") is None


def test_catalog_lists_a_track_that_is_not_linked_to_a_figure() -> None:
    catalog = """
tracks:
  - path: stories/bear.mp3
    title: Bear
  - uid: "04aabbccddeeff"
    path: stories/frog-prince.mp3
    title: The Frog Prince
"""
    library = import_catalog(
        catalog,
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: True,
    )

    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_library_files_missing_from_the_catalog_are_recorded_there() -> None:
    catalog = """
tracks:
- uid: 6cde55fa
  path: romys-birthday-party.mp3
  title: romys birthday party
  artist: null
tags:
- uid: 6cde55fa
  name: Skateboard
"""
    updated = include_library_tracks(
        catalog,
        ["library/romys-birthday-party.mp3", "library/little-drummer-girl.mp3"],
    )
    data = yaml.safe_load(updated)
    rows = {row["path"]: row for row in data["tracks"]}

    assert rows["library/romys-birthday-party.mp3"]["uid"] == "6cde55fa"
    assert rows["library/romys-birthday-party.mp3"]["title"] == "romys birthday party"
    assert rows["library/little-drummer-girl.mp3"]["title"] == "little drummer girl"
    assert "uid" not in rows["library/little-drummer-girl.mp3"]
    assert data["tags"][0]["name"] == "Skateboard"


def test_a_removed_track_stays_out_when_its_file_is_still_on_disk() -> None:
    catalog = """
tracks:
- uid: bbbb
  path: robot.mp3
  title: Robot
tags:
- uid: aaaa
  name: Blue Tag
- uid: bbbb
  name: Red Robot
removed:
- banana.mp3
"""
    updated = include_library_tracks(catalog, ["banana.mp3", "robot.mp3"])
    data = yaml.safe_load(updated)

    assert [row["path"] for row in data["tracks"]] == ["robot.mp3"]
    assert data["tags"][0]["name"] == "Blue Tag"
    assert data["removed"] == ["banana.mp3"]
