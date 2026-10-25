import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from romini.composition.dashboard import create_dashboard
from romini.composition.dashboard.shared import DiskStorage, PathCatalog


def test_dashboard_downloads_a_backup_of_stories_and_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("tracks: []\n")
    story = tmp_path / "stories" / "frog" / "story.yaml"
    story.parent.mkdir(parents=True)
    story.write_text("title: Frog\n")
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(tmp_path / "library"),
            assign_catalog=PathCatalog(catalog),
            stories=tmp_path / "stories",
            characters=tmp_path / "characters",
        )
    )

    response = client.get("/backup")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "romini-backup.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as saved:
        assert saved.read("stories/frog/story.yaml") == b"title: Frog\n"
        assert saved.read("catalog.yaml") == b"tracks: []\n"


def test_dashboard_import_restores_stories_and_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("tracks: []\n")
    stories = tmp_path / "stories"
    stories.mkdir()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as saved:
        saved.writestr("catalog.yaml", "tracks:\n  - uid: aa\n")
        saved.writestr("stories/frog/story.yaml", "title: Frog\n")
        saved.writestr("characters/romy/character.yaml", "name: Romy\nbackground: The main character\n")
    client = TestClient(
        create_dashboard(
            storage=DiskStorage(tmp_path / "library"),
            assign_catalog=PathCatalog(catalog),
            stories=stories,
            characters=tmp_path / "characters",
        )
    )

    response = client.post(
        "/backup",
        files={"file": ("romini-backup.zip", archive.getvalue(), "application/zip")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/settings?notice=backup")
    assert catalog.read_text() == "tracks:\n  - uid: aa\n"
    assert (stories / "frog" / "story.yaml").read_text() == "title: Frog\n"
    character = tmp_path / "characters" / "romy" / "character.yaml"
    assert character.read_text() == "name: Romy\nbackground: The main character\n"


def test_settings_page_offers_backup_download_and_restore(tmp_path: Path) -> None:
    client = TestClient(create_dashboard(storage=DiskStorage(tmp_path)))

    html = client.get("/settings").text
    restored = client.get("/settings?notice=backup").text

    assert 'id="backup"' in html
    assert 'action="/backup"' in html
    assert 'method="get"' in html
    assert 'name="file"' in html
    assert "Backup restored" in restored
