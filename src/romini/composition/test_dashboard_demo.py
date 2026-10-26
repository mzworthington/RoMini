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


def test_demo_loads_cookieless_posthog_and_a_privacy_notice() -> None:
    client = TestClient(create_dashboard(storage=MemoryStorage(), demo=True, posthog_token=" phc_test "))

    home = client.get("/")
    config = client.get("/posthog-config.json")
    privacy = client.get("/privacy")

    assert home.status_code == 200
    assert 'href="/privacy"' in home.text
    assert "cookieless_mode" in home.text
    assert 'person_profiles: "never"' in home.text
    assert "disable_session_recording: true" in home.text
    assert config.status_code == 200
    assert config.headers["cache-control"] == "no-store"
    assert config.json() == {
        "enabled": True,
        "apiKey": "phc_test",
        "apiHost": "https://a.mzworthington.co.uk",
    }
    assert privacy.status_code == 200
    assert "Session replay is off" in privacy.text
    assert "romini.local" in privacy.text
    assert "identify()" in privacy.text


def test_demo_without_a_token_does_not_enable_posthog() -> None:
    client = TestClient(create_dashboard(storage=MemoryStorage(), demo=True))

    assert client.get("/posthog-config.json").json() == {"enabled": False}


def test_house_dashboard_does_not_load_posthog() -> None:
    client = TestClient(create_dashboard(storage=MemoryStorage(), demo=False, posthog_token="phc_test"))
    home = client.get("/")

    assert "posthog" not in home.text.lower()
    assert client.get("/posthog-config.json").status_code == 404
    assert client.get("/privacy").status_code == 404


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


def test_demo_pages_do_not_spawn_host_probes(monkeypatch) -> None:
    from romini.composition.dashboard import shared

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("demo pages must not spawn a process")

    monkeypatch.setattr(shared.subprocess, "run", explode)
    client = TestClient(create_dashboard(storage=MemoryStorage(), demo=True))

    settings = client.get("/settings")
    figures = client.get("/figures")

    assert settings.status_code == 200
    assert figures.status_code == 200
    assert "System &amp; Hardware" in settings.text
    assert "Figures" in figures.text


def test_house_settings_still_reads_the_player_log(monkeypatch) -> None:
    from romini.composition.dashboard import shared

    seen: list[list[str]] = []

    def run(args: list[str], **_kwargs: object) -> object:
        seen.append(list(args))

        class Completed:
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(shared.subprocess, "run", run)
    response = TestClient(create_dashboard(storage=MemoryStorage(), demo=False)).get("/settings")

    assert response.status_code == 200
    assert ["journalctl", "-u", "romini-core.service"] in [call[:3] for call in seen]


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
