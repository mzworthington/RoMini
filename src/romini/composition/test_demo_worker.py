import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from romini.composition.demo_worker import app_for_env


def test_default_fetch_registers_a_worker_entrypoint() -> None:
    source = Path(__file__).with_name("demo_worker.py").read_text()

    assert "class Default(WorkerEntrypoint)" in source


def test_worker_env_builds_the_seeded_demo() -> None:
    class Prepared:
        def all(self) -> object:
            async def go() -> dict[str, list[dict[str, str]]]:
                return {
                    "results": [
                        {
                            "key": "catalog",
                            "value": "tracks:\n  - uid: '04a1'\n    path: frog.mp3\n    title: Frog\n",
                        },
                        {"key": "play_mode", "value": "presence"},
                    ]
                }

            return go()

    class Database:
        def prepare(self, sql: str) -> Prepared:
            assert sql == "SELECT key, value FROM settings"
            return Prepared()

    class Bucket:
        def list(self) -> object:
            async def go() -> dict[str, list[dict[str, object]]]:
                return {"objects": [{"key": "frog.mp3", "size": 4}]}

            return go()

    class Env:
        DB = Database()
        LIBRARY = Bucket()
        LIBRARY_BASE_URL = "https://media.example"

    app = asyncio.run(app_for_env(Env()))
    html = TestClient(app).get("/library").text

    assert "Frog" in html
    assert 'data-demo-play="https://media.example/frog.mp3"' in html
    assert TestClient(app).get("/posthog-config.json").json() == {"enabled": False}


def test_worker_env_passes_the_posthog_token_to_the_demo() -> None:
    class Prepared:
        def all(self) -> object:
            async def go() -> dict[str, list[dict[str, str]]]:
                return {"results": []}

            return go()

    class Database:
        def prepare(self, sql: str) -> Prepared:
            assert sql == "SELECT key, value FROM settings"
            return Prepared()

    class Bucket:
        def list(self) -> object:
            async def go() -> dict[str, list[dict[str, object]]]:
                return {"objects": []}

            return go()

    class Env:
        DB = Database()
        LIBRARY = Bucket()
        LIBRARY_BASE_URL = "https://media.example"
        POSTHOG_TOKEN = " phc_test "
        POSTHOG_HOST = " https://eu.i.posthog.com "

    app = asyncio.run(app_for_env(Env()))

    assert TestClient(app).get("/posthog-config.json").json() == {
        "enabled": True,
        "apiKey": "phc_test",
        "apiHost": "https://eu.i.posthog.com",
    }
