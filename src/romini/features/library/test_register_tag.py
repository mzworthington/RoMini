import yaml

from romini.features.library.register_tag import name_tag, register_tag


class FakeCatalogFile:
    def __init__(self) -> None:
        self.text = "tracks: []\n"

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> None:
        self.text = text


def test_register_tag_lists_uid_in_catalog_tags() -> None:
    catalog = FakeCatalogFile()

    register_tag(uid="04aabbccddeeff", catalog=catalog)

    data = yaml.safe_load(catalog.text) or {}
    assert data["tags"] == [{"uid": "04aabbccddeeff", "name": ""}]
    assert data["tracks"] == []


def test_register_tag_keeps_existing_name_on_duplicate_uid() -> None:
    catalog = FakeCatalogFile()
    catalog.text = "tags:\n  - uid: 04aabbccddeeff\n    name: Frog Prince\ntracks: []\n"

    register_tag(uid="04aabbccddeeff", catalog=catalog)

    data = yaml.safe_load(catalog.text) or {}
    assert data["tags"] == [{"uid": "04aabbccddeeff", "name": "Frog Prince"}]


class FakeLed:
    def __init__(self) -> None:
        self.pulses = 0

    def pulse(self) -> None:
        self.pulses += 1


class FakeEarcon:
    def __init__(self) -> None:
        self.plays: list[str] = []

    def play_earcon(self, path: str) -> None:
        self.plays.append(path)


def test_register_tag_plays_connect_and_pulses_led() -> None:
    catalog = FakeCatalogFile()
    led = FakeLed()
    earcon = FakeEarcon()

    register_tag(uid="04aabbccddeeff", catalog=catalog, led=led, earcon=earcon)

    assert led.pulses == 1
    assert earcon.plays == ["romini/connect.wav"]


def test_name_tag_updates_registered_tag_name() -> None:
    catalog = FakeCatalogFile()
    catalog.text = "tags:\n  - uid: 04aabbccddeeff\n    name: ''\ntracks: []\n"

    name_tag(uid="04aabbccddeeff", name="Frog Prince", catalog=catalog)

    data = yaml.safe_load(catalog.text) or {}
    assert data["tags"] == [{"uid": "04aabbccddeeff", "name": "Frog Prince"}]
