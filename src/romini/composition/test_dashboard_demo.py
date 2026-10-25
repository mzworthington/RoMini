from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from romini.composition.dashboard import create_dashboard


@dataclass
class MemoryStorage:
    files: dict[str, bytes] = field(default_factory=dict)
    free_bytes: int = 1024

    def put(self, filename: str, audio: bytes) -> None:
        self.files[filename] = audio

    def paths(self) -> list[str]:
        return sorted(self.files)

    def get(self, filename: str) -> bytes | None:
        return self.files.get(filename)


def test_demo_home_names_itself_and_refuses_an_upload() -> None:
    storage = MemoryStorage()
    client = TestClient(create_dashboard(storage=storage, demo=True))

    home = client.get("/")

    assert home.status_code == 200
    assert "Public demo" in home.text
    assert "Studio keys, uploads, and other changes are turned off" in home.text

    uploaded = client.post("/tracks", files={"file": ("frog.mp3", b"id3", "audio/mpeg")})

    assert uploaded.status_code == 200
    assert "turned off on this demo" in uploaded.text
    assert storage.files == {}


def test_demo_hides_key_upload_and_narration_controls() -> None:
    client = TestClient(create_dashboard(storage=MemoryStorage(), demo=True))

    library = client.get("/library").text
    settings = client.get("/settings").text
    stories = client.get("/stories").text

    assert "Uploads are turned off" in library
    assert 'action="/tracks"' not in library
    assert "Studio keys are turned off" in settings
    assert 'action="/keys"' not in settings
    assert "Drafting and speaking are turned off" in stories
    assert 'action="/stories/draft"' not in stories
    assert 'action="/stories/speak"' not in stories
    assert "Download backup" in settings
    assert "Restore is turned off on this demo" in settings
    assert 'id="backup-file"' not in settings
    restored = client.post(
        "/backup",
        files={"file": ("romini-backup.zip", b"PK", "application/zip")},
    )
    assert "turned off on this demo" in restored.text
    assert "turned off on this demo" in client.post("/keys", data={"gemini_key": "secret"}).text
    assert "turned off on this demo" in client.post("/stories/draft").text
