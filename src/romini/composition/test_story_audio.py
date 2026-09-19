from collections.abc import Sequence
from pathlib import Path
from random import Random


def test_story_audio_writes_mp3_with_the_same_name(tmp_path: Path) -> None:
    from romini.composition.story_audio import render_story

    story = tmp_path / "romy-and-the-little-station.md"
    story.write_text("# Title\n\n## Script\n\nRowmy found a banana.\n")

    class FakeSpeech:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            return b"ID3fake"

    out = render_story(
        story,
        speech=FakeSpeech(),
        voices=("voice-a", "voice-b"),
        rng=Random(0),
    )

    assert out == tmp_path / "romy-and-the-little-station.mp3"
    assert out.read_bytes() == b"ID3fake"


def test_story_audio_assigns_a_voice_from_the_array(tmp_path: Path) -> None:
    from romini.composition.story_audio import render_story

    story = tmp_path / "tale.md"
    story.write_text("## Script\n\nHello.\n")
    chosen: list[str] = []

    class FakeSpeech:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            chosen.append(voice_id)
            return b"x"

    class PickSecond(Random):
        def choice(self, seq: Sequence[str]) -> str:
            return seq[1]

    render_story(
        story,
        speech=FakeSpeech(),
        voices=("voice-a", "voice-b", "voice-c"),
        rng=PickSecond(),
    )

    assert chosen == ["voice-b"]


def test_story_audio_logs_the_chosen_voice_and_output_path(tmp_path: Path, caplog) -> None:
    import logging

    from romini.composition.story_audio import render_story

    caplog.set_level(logging.INFO)
    story = tmp_path / "tale.md"
    story.write_text("## Script\n\nHello.\n")

    class FakeSpeech:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            return b"x"

    class PickFirst(Random):
        def choice(self, seq: Sequence[str]) -> str:
            return seq[0]

    render_story(story, speech=FakeSpeech(), voices=("voice-a",), rng=PickFirst())

    assert "tale.md" in caplog.text
    assert "voice-a" in caplog.text
    assert "tale.mp3" in caplog.text


def test_story_audio_logs_when_speech_fails(tmp_path: Path, caplog) -> None:
    import logging

    import pytest

    from romini.composition.story_audio import render_story

    caplog.set_level(logging.ERROR)
    story = tmp_path / "tale.md"
    story.write_text("## Script\n\nHello.\n")

    class Boom:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            raise RuntimeError("quota")

    class PickFirst(Random):
        def choice(self, seq: Sequence[str]) -> str:
            return seq[0]

    with pytest.raises(RuntimeError, match="quota"):
        render_story(story, speech=Boom(), voices=("voice-a",), rng=PickFirst())

    assert "tale.md" in caplog.text
    assert "voice-a" in caplog.text
    assert "quota" in caplog.text


def test_http_post_logs_error_body_without_the_api_key(monkeypatch, caplog) -> None:
    import logging
    from io import BytesIO
    from urllib.error import HTTPError

    import pytest

    from romini.composition.story_audio import http_post

    caplog.set_level(logging.ERROR)

    def fake_urlopen(request: object, timeout: object = None) -> object:
        raise HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/voice-b",
            401,
            "Unauthorized",
            hdrs=None,
            fp=BytesIO(b'{"detail":"invalid_api_key"}'),
        )

    monkeypatch.setattr("romini.composition.story_audio.urlopen", fake_urlopen)
    with pytest.raises(HTTPError):
        http_post(
            "https://api.elevenlabs.io/v1/text-to-speech/voice-b?output_format=mp3_44100_128",
            headers={"xi-api-key": "sk_test", "Content-Type": "application/json"},
            body=b"{}",
        )

    assert "401" in caplog.text
    assert "invalid_api_key" in caplog.text
    assert "sk_test" not in caplog.text


def test_elevenlabs_speech_posts_v3_for_the_chosen_voice() -> None:
    from romini.composition.story_audio import ElevenLabsSpeech

    calls: list[tuple[str, dict[str, str], bytes]] = []

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        calls.append((url, headers, body))
        return b"ID3ok"

    audio = ElevenLabsSpeech(api_key="sk_test", post=post).speak(
        text="Rowmy found a banana.",
        voice_id="voice-b",
    )

    assert audio == b"ID3ok"
    url, headers, body = calls[0]
    assert "voice-b" in url
    assert "output_format=mp3_44100_128" in url
    assert headers["xi-api-key"] == "sk_test"
    assert b'"model_id": "eleven_v3"' in body
    assert b"Rowmy found a banana." in body


def test_story_audio_writes_mp3_for_each_story_in_the_folder(tmp_path: Path) -> None:
    from romini.composition.story_audio import render_stories

    stories = tmp_path / "stories"
    stories.mkdir()
    (stories / "README.md").write_text("# Stories\n")
    (stories / "romy-and-the-little-station.md").write_text("## Script\n\nHello.\n")
    (stories / "romy-and-the-blue-window.md").write_text("## Script\n\nTiles.\n")

    class FakeSpeech:
        def speak(self, *, text: str, voice_id: str) -> bytes:
            return text.encode()

    render_stories(stories, speech=FakeSpeech(), voices=("voice-a",), rng=Random(0))

    assert (stories / "romy-and-the-little-station.mp3").read_bytes() == b"Hello."
    assert (stories / "romy-and-the-blue-window.mp3").read_bytes() == b"Tiles."
    assert not (stories / "README.mp3").exists()


def test_story_audio_main_renders_folder_using_voice_ids(tmp_path: Path, monkeypatch) -> None:
    from romini.composition.story_audio import main

    stories = tmp_path / "stories"
    stories.mkdir()
    (stories / "tale.md").write_text("## Script\n\nHello.\n")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    monkeypatch.setenv("ELEVENLABS_VOICE_IDS", "voice-a,voice-b")
    posted: list[str] = []

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        posted.append(url)
        return b"ID3ok"

    main(["--folder", str(stories)], post=post)

    assert (stories / "tale.mp3").read_bytes() == b"ID3ok"
    assert any("voice-a" in url or "voice-b" in url for url in posted)


def test_story_audio_main_logs_the_folder_without_the_api_key(tmp_path: Path, monkeypatch, caplog) -> None:
    import logging

    from romini.composition.story_audio import main

    caplog.set_level(logging.INFO)
    stories = tmp_path / "stories"
    stories.mkdir()
    (stories / "tale.md").write_text("## Script\n\nHello.\n")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_test")
    monkeypatch.setenv("ELEVENLABS_VOICE_IDS", "voice-a,voice-b")

    def post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
        return b"ID3ok"

    main(["--folder", str(stories)], post=post)

    assert str(stories) in caplog.text
    assert "2 voice" in caplog.text
    assert "sk_test" not in caplog.text


def test_story_audio_reads_only_the_script_body() -> None:
    from romini.composition.story_audio import script_body

    markdown = "# Romy and the Banana\n\n- Cast: Romy\n- Say: Romy is Rowmy.\n\n## Script\n\nRowmy found a banana.\n"

    assert script_body(markdown) == "Rowmy found a banana."


def test_story_audio_loads_named_voices_from_yaml(tmp_path: Path) -> None:
    from romini.composition.story_audio import load_voices

    path = tmp_path / "voices.yaml"
    path.write_text("voices:\n  - name: Rowmy\n    id: voice-rowmy\n  - name: Maama\n    id: voice-maama\n")

    assert load_voices(path) == [
        {"name": "Rowmy", "id": "voice-rowmy"},
        {"name": "Maama", "id": "voice-maama"},
    ]


def test_story_audio_ships_named_household_voices() -> None:
    from romini.composition.story_audio import load_voices

    voices = load_voices()
    names = [voice["name"] for voice in voices]
    ids = [voice["id"] for voice in voices]

    assert names == ["Rowmy", "Maama", "Baaba"]
    assert ids == [
        "qXdtsJJ9LgnQ8Z2TYfav",
        "ZF6FPAbjXT4488VcRRnw",
        "AXdMgz6evoL7OPd7eU12",
    ]
