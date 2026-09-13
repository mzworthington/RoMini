"""Tests for the Flask web layer."""

import pytest

from romini.app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "RoMini" in body
    assert "Whispering Forest" in body  # theme chips rendered


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "version" in data


def test_api_story_returns_story(client):
    resp = client.post("/api/story", json={"hero": "Romy", "theme": "space"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hero"] == "Romy"
    assert data["theme"] == "space"
    assert len(data["paragraphs"]) == 5


def test_api_story_seed_is_deterministic(client):
    r1 = client.post("/api/story", json={"hero": "Romy", "theme": "ocean", "seed": 5})
    r2 = client.post("/api/story", json={"hero": "Romy", "theme": "ocean", "seed": 5})
    assert r1.get_json() == r2.get_json()


def test_api_story_handles_empty_body(client):
    resp = client.post("/api/story")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["hero"] == "Romy"  # default hero


def test_api_story_ignores_bad_seed(client):
    resp = client.post(
        "/api/story", json={"hero": "Romy", "theme": "forest", "seed": "abc"}
    )
    assert resp.status_code == 200
    assert len(resp.get_json()["paragraphs"]) == 5
