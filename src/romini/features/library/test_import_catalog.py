import pytest

from romini.features.library.import_catalog import import_catalog


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
