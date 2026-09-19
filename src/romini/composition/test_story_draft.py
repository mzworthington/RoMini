import json


def test_gemini_script_draft_posts_notes_and_returns_text() -> None:
    from romini.composition.story_draft import GeminiScriptDraft

    calls: list[tuple[str, dict[str, str], bytes]] = []

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        calls.append((url, headers, body))
        return json.dumps(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "Rowmy waited at the station. [pause]"}],
                        }
                    }
                ]
            }
        ).encode()

    script = GeminiScriptDraft(api_key="gem-secret", post=post).draft(
        title="The little station",
        characters="Romy",
        interests="trains",
        outline="a ride",
    )

    assert script == "Rowmy waited at the station. [pause]"
    url, headers, body = calls[0]
    payload = json.loads(body)
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent" in url
    assert headers["x-goog-api-key"] == "gem-secret"
    assert "The little station" in prompt
    assert "Romy" in prompt
    assert "trains" in prompt
    assert "a ride" in prompt
    assert "Rowmy" in prompt
    assert "Maama" in prompt
    assert "Baaba" in prompt
    assert "[pause]" in prompt
    assert "gem-secret" not in url
