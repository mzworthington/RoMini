import yaml

from romini.features.library.assign import confirm_assign, remove_track
from romini.features.library.import_catalog import import_catalog


class FakeCatalogFile:
    def __init__(self) -> None:
        self.text = "tracks: []"

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.text = text


def test_assign_confirm_lists_tag_and_track_in_catalog() -> None:
    catalog = FakeCatalogFile()

    confirm_assign(
        uid="04aabbccddeeff",
        path="stories/frog-prince.mp3",
        title="The Frog Prince",
        catalog=catalog,
    )

    library = import_catalog(
        catalog.text,
        library_root="/var/lib/romini/library",
        audio_exists=lambda path: path == "stories/frog-prince.mp3",
    )
    assert library.track_for("04aabbccddeeff") == "/var/lib/romini/library/stories/frog-prince.mp3"


def test_assign_confirm_preserves_registered_tags() -> None:
    catalog = FakeCatalogFile()
    catalog.text = "tags:\n  - uid: 04aabbccddeeff\n    name: Frog Prince\ntracks: []\n"

    confirm_assign(
        uid="04aabbccddeeff",
        path="stories/frog-prince.mp3",
        title="The Frog Prince",
        catalog=catalog,
    )

    data = yaml.safe_load(catalog.text) or {}
    assert data["tags"] == [{"uid": "04aabbccddeeff", "name": "Frog Prince"}]


def test_assign_confirm_keeps_the_cover_when_the_path_stays() -> None:
    catalog = FakeCatalogFile()
    catalog.text = (
        "tracks:\n"
        "  - uid: 04aabbccddeeff\n"
        "    path: stories/frog-prince.mp3\n"
        "    title: The Frog Prince\n"
        "    artist:\n"
        "    image:\n"
        "      file: cover.png\n"
        "      size: 12\n"
        "      media_type: image/png\n"
    )

    confirm_assign(
        uid="04aabbccddeeff",
        path="stories/frog-prince.mp3",
        title="The Frog Prince",
        catalog=catalog,
    )

    image = (yaml.safe_load(catalog.text) or {})["tracks"][0]["image"]
    assert image["file"] == "cover.png"
    assert image["media_type"] == "image/png"
    assert "story" not in image


def test_assign_confirm_drops_the_cover_when_the_audio_changes() -> None:
    catalog = FakeCatalogFile()
    catalog.text = (
        "tracks:\n"
        "  - uid: 04aabbccddeeff\n"
        "    path: stories/frog-prince.mp3\n"
        "    title: The Frog Prince\n"
        "    image:\n"
        "      file: cover.png\n"
        "      size: 12\n"
        "      media_type: image/png\n"
    )

    confirm_assign(
        uid="04aabbccddeeff",
        path="stories/other.mp3",
        title="Other",
        catalog=catalog,
    )

    assert "image" not in (yaml.safe_load(catalog.text) or {})["tracks"][0]


def test_remove_track_keeps_every_figure_and_does_not_list_that_path_again() -> None:
    catalog = FakeCatalogFile()
    catalog.text = (
        "tags:\n"
        "  - uid: aaaa\n"
        "    name: Blue Tag\n"
        "  - uid: bbbb\n"
        "    name: Red Robot\n"
        "tracks:\n"
        "  - uid: aaaa\n"
        "    path: banana.mp3\n"
        "    title: Banana\n"
        "  - uid: bbbb\n"
        "    path: robot.mp3\n"
        "    title: Robot\n"
    )

    remove_track(path="banana.mp3", catalog=catalog)
    remove_track(path="", catalog=catalog)

    data = yaml.safe_load(catalog.text) or {}
    assert [row["path"] for row in data["tracks"]] == ["robot.mp3"]
    assert data["tags"] == [
        {"uid": "aaaa", "name": "Blue Tag"},
        {"uid": "bbbb", "name": "Red Robot"},
    ]
    assert data["removed"] == ["banana.mp3"]
