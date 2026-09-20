import json


def test_ten_second_story_aims_for_twenty_spoken_words() -> None:
    from romini.composition.story_draft import spoken_word_target

    assert spoken_word_target(duration_seconds=10) == 20


def test_ten_minute_story_aims_for_twelve_hundred_spoken_words() -> None:
    from romini.composition.story_draft import spoken_word_target

    assert spoken_word_target(duration_seconds=600) == 1200


def test_story_length_clamps_to_ten_seconds_and_ten_minutes() -> None:
    from romini.composition.story_draft import spoken_word_target

    assert spoken_word_target(duration_seconds=1) == 20
    assert spoken_word_target(duration_seconds=900) == 1200


def test_story_length_label_uses_seconds_under_a_minute() -> None:
    from romini.composition.story_draft import listen_length_label

    assert listen_length_label(duration_seconds=10) == "10 seconds"


def test_story_length_label_uses_minutes_for_whole_minutes() -> None:
    from romini.composition.story_draft import listen_length_label

    assert listen_length_label(duration_seconds=60) == "1 minute"
    assert listen_length_label(duration_seconds=600) == "10 minutes"


def test_story_length_label_includes_leftover_seconds() -> None:
    from romini.composition.story_draft import listen_length_label

    assert listen_length_label(duration_seconds=90) == "1 minute 30 seconds"


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


def test_gemini_script_draft_asks_for_target_spoken_words() -> None:
    from romini.composition.story_draft import GeminiScriptDraft

    calls: list[bytes] = []

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        calls.append(body)
        return json.dumps({"candidates": [{"content": {"parts": [{"text": "Once upon a time"}]}}]}).encode()

    GeminiScriptDraft(api_key="gem-secret", post=post).draft(
        title="The little station",
        characters="Romy",
        interests="trains",
        outline="a ride",
        duration_seconds=240,
    )

    prompt = json.loads(calls[0])["contents"][0]["parts"][0]["text"]
    assert "about 480 spoken words" in prompt
    assert "4 minutes" in prompt
