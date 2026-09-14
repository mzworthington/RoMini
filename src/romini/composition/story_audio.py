import argparse
import json
import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from random import Random
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VOICE_IDS: tuple[str, ...] = (
    # Fill with ElevenLabs Voice Lab IDs, or set ELEVENLABS_VOICE_IDS.
)

REPO_STORIES = Path(__file__).resolve().parents[3] / "docs" / "stories"
log = logging.getLogger(__name__)


class Speech(Protocol):
    def speak(self, *, text: str, voice_id: str) -> bytes: ...


class ElevenLabsSpeech:
    def __init__(self, *, api_key: str, post: Callable[..., bytes]) -> None:
        self._api_key = api_key
        self._post = post

    def speak(self, *, text: str, voice_id: str) -> bytes:
        return self._post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            body=json.dumps({"text": text, "model_id": "eleven_v3"}).encode(),
        )


def script_body(markdown: str) -> str:
    marker = "## Script"
    if marker not in markdown:
        return markdown.strip()
    return markdown.split(marker, 1)[1].strip()


def render_story(
    markdown: Path,
    *,
    speech: Speech,
    voices: Sequence[str],
    rng: Random,
) -> Path:
    voice_id = rng.choice(list(voices))
    log.info("Rendering %s with voice %s", markdown.name, voice_id)
    try:
        audio = speech.speak(text=script_body(markdown.read_text()), voice_id=voice_id)
    except Exception:
        log.exception("Failed to render %s with voice %s", markdown.name, voice_id)
        raise
    out = markdown.with_suffix(".mp3")
    out.write_bytes(audio)
    log.info("Wrote %s", out)
    return out


def render_stories(
    folder: Path,
    *,
    speech: Speech,
    voices: Sequence[str],
    rng: Random,
) -> None:
    for story in sorted(folder.glob("*.md")):
        if story.name.lower() == "readme.md":
            continue
        render_story(story, speech=speech, voices=voices, rng=rng)


def configured_voices() -> tuple[str, ...]:
    raw = os.environ.get("ELEVENLABS_VOICE_IDS", "")
    from_env = tuple(part.strip() for part in raw.split(",") if part.strip())
    return from_env or VOICE_IDS


def http_post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request) as response:
            return response.read()
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        log.error("ElevenLabs HTTP %s for %s: %s", err.code, url.split("?", 1)[0], detail)
        raise


def main(argv: list[str] | None = None, *, post: Callable[..., bytes] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render docs/stories markdown to same-name MP3s.")
    parser.add_argument("--folder", type=Path, default=REPO_STORIES)
    args = parser.parse_args(argv)
    voices = configured_voices()
    if not voices:
        raise SystemExit("set ELEVENLABS_VOICE_IDS or fill VOICE_IDS")
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("set ELEVENLABS_API_KEY")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log.info("Rendering stories in %s with %s voices", args.folder, len(voices))
    render_stories(
        args.folder,
        speech=ElevenLabsSpeech(api_key=api_key, post=post or http_post),
        voices=voices,
        rng=Random(),
    )


if __name__ == "__main__":
    main()
