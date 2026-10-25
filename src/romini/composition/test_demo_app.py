def test_demo_backup_keeps_the_seeded_studio_and_catalog() -> None:
    import io
    import zipfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from romini.composition.demo_app import create_demo_app

    catalog = (Path(__file__).resolve().parents[3] / "deploy/demo/catalog.yaml").read_text()
    client = TestClient(
        create_demo_app(
            settings_rows=[("catalog", catalog), ("play_mode", "presence")],
            objects=[],
            base_url="https://media.example",
        )
    )

    response = client.get("/backup")

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as saved:
        names = set(saved.namelist())
        assert "characters/romy/character.yaml" in names
        assert "stories/romy-and-the-banana/story.yaml" in names
        assert b"name: Romy" in saved.read("characters/romy/character.yaml")
        assert saved.read("catalog.yaml").decode() == catalog


def test_opening_a_demo_story_leaves_the_packaged_seed_unchanged(tmp_path) -> None:
    import shutil
    from pathlib import Path

    from fastapi.testclient import TestClient

    from romini.composition import demo_app

    seed = tmp_path / "demo_content"
    shutil.copytree(demo_app._CONTENT, seed)
    pointer = seed / "stories" / "current"
    before = pointer.read_text()
    demo_app._CONTENT = seed
    try:
        client = TestClient(
            demo_app.create_demo_app(
                settings_rows=[("catalog", "tracks: []\n"), ("play_mode", "presence")],
                objects=[],
                base_url="https://media.example",
            )
        )
        response = client.get("/stories/romy-and-the-robot")
    finally:
        demo_app._CONTENT = Path(__file__).resolve().parent / "demo_content"

    assert response.status_code == 200
    assert "A small robot visits at bedtime." in response.text
    assert pointer.read_text() == before


def test_demo_catalog_shows_stories_figures_and_tracks() -> None:
    from pathlib import Path

    import yaml
    from fastapi.testclient import TestClient

    from romini.composition.demo_app import create_demo_app

    catalog_path = Path(__file__).resolve().parents[3] / "deploy/demo/catalog.yaml"
    catalog = catalog_path.read_text()
    data = yaml.safe_load(catalog)
    objects = [{"key": track["path"], "size": 128} for track in data["tracks"]]
    app = create_demo_app(
        settings_rows=[("catalog", catalog), ("play_mode", "presence")],
        objects=objects,
        base_url="https://media.example",
    )
    client = TestClient(app)
    figures = client.get("/figures").text
    library = client.get("/library").text
    stories = client.get("/stories").text

    assert "romys-birthday-party" not in catalog
    assert "Blue Tag" in figures
    assert "Romy and the banana" in figures
    assert 'data-demo-play="https://media.example/romy-and-the-banana.mp3"' in library
    assert "Romy and the brick tower" in stories
    assert "Romy" in stories
    assert '<span class="metric">5</span>' in stories
    assert '<span class="metric">3</span>' in stories
    assert 'name="character" value="romy" checked' in stories


def test_demo_app_renders_the_seeded_library() -> None:
    from fastapi.testclient import TestClient

    from romini.composition.demo_app import create_demo_app

    app = create_demo_app(
        settings_rows=[
            ("catalog", "tracks:\n  - uid: '04a1'\n    path: frog.mp3\n    title: Frog\n"),
            ("play_mode", "presence"),
        ],
        objects=[
            {"key": "frog.mp3", "size": 4},
            {"key": "covers/frog.mp3/cover.png", "size": 8},
        ],
        base_url="https://media.example",
    )
    client = TestClient(app)
    html = client.get("/library").text

    assert "Frog" in html
    assert 'data-demo-play="https://media.example/frog.mp3"' in html
    assert 'src="https://media.example/covers/frog.mp3/cover.png"' in html
    assert 'fetch("/now-playing")' not in client.get("/").text
    preview = client.get("/library/file/frog.mp3", follow_redirects=False)
    assert preview.status_code == 302
    assert preview.headers["location"] == "https://media.example/frog.mp3"


def test_demo_home_plays_the_seeded_track_in_the_page() -> None:
    from fastapi.testclient import TestClient

    from romini.composition.demo_app import create_demo_app

    app = create_demo_app(
        settings_rows=[
            ("catalog", "tracks:\n  - uid: '04a1'\n    path: frog.mp3\n    title: Frog\n"),
            ("play_mode", "presence"),
        ],
        objects=[{"key": "frog.mp3", "size": 4}],
        base_url="https://media.example",
    )
    html = TestClient(app).get("/").text

    assert "<audio" in html
    assert 'src="https://media.example/frog.mp3"' in html
    assert 'action="/play"' not in html
