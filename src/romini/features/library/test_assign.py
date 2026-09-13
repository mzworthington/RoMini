from romini.features.library.assign import confirm_assign
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
