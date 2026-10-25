def test_demo_story_page_opens_when_the_pointer_cannot_be_saved(monkeypatch) -> None:
    from pathlib import Path

    from fastapi.testclient import TestClient

    from romini.composition.demo_app import create_demo_app

    real_write = Path.write_text

    def read_only_pointer(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == "current":
            raise OSError(30, "Read-only file system")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", read_only_pointer)
    client = TestClient(
        create_demo_app(
            settings_rows=[("catalog", "tracks: []\n"), ("play_mode", "presence")],
            objects=[],
            base_url="https://media.example",
        )
    )

    banana = client.get("/stories/romy-and-the-banana")
    robot = client.get("/stories/romy-and-the-robot")
    character = client.get("/characters/baba")

    assert banana.status_code == 200
    assert 'value="Romy and the banana"' in banana.text
    assert robot.status_code == 200
    assert "A small robot visits at bedtime." in robot.text
    assert character.status_code == 200
    assert 'value="Baba"' in character.text


def test_writable_studio_can_update_a_read_only_seed(tmp_path) -> None:
    from romini.composition.demo_app import _writable_studio

    seed = tmp_path / "seed"
    story = seed / "stories" / "tale"
    story.mkdir(parents=True)
    notes = story / "story.yaml"
    pointer = seed / "stories" / "current"
    notes.write_text("title: Tale\n")
    pointer.write_text("tale\n")
    notes.chmod(0o444)
    pointer.chmod(0o444)
    (seed / "stories").chmod(0o555)
    (seed / "characters").mkdir()
    try:
        copied = _writable_studio(seed)
        current = copied / "stories" / "current"
        current.write_text("next\n")
        assert current.read_text() == "next\n"
    finally:
        (seed / "stories").chmod(0o755)
        notes.chmod(0o644)
        pointer.chmod(0o644)


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
