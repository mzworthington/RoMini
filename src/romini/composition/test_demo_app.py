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
