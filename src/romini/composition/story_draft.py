import json
import logging
from collections.abc import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from romini.composition.story_audio import vendor_error_message

log = logging.getLogger(__name__)

WORDS_PER_MINUTE = 120
MIN_DURATION_SECONDS = 10
MAX_DURATION_SECONDS = 600


def clamp_duration_seconds(duration_seconds: int) -> int:
    return min(MAX_DURATION_SECONDS, max(MIN_DURATION_SECONDS, duration_seconds))


def parse_duration_seconds(value: object) -> int:
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        seconds = MIN_DURATION_SECONDS
    return clamp_duration_seconds(seconds)


def spoken_word_target(*, duration_seconds: int) -> int:
    return round(clamp_duration_seconds(duration_seconds) * WORDS_PER_MINUTE / 60)


def listen_length_label(*, duration_seconds: int) -> str:
    clamped = clamp_duration_seconds(duration_seconds)
    if clamped < 60:
        return f"{clamped} seconds"
    minutes, seconds = divmod(clamped, 60)
    unit = "minute" if minutes == 1 else "minutes"
    if seconds == 0:
        return f"{minutes} {unit}"
    return f"{minutes} {unit} {seconds} seconds"


class GeminiScriptDraft:
    def __init__(self, *, api_key: str, post: Callable[..., bytes]) -> None:
        self._api_key = api_key
        self._post = post

    def draft(
        self,
        *,
        title: str,
        characters: str,
        interests: str,
        outline: str,
        duration_seconds: int = MIN_DURATION_SECONDS,
    ) -> str:
        words = spoken_word_target(duration_seconds=duration_seconds)
        length = listen_length_label(duration_seconds=duration_seconds)
        prompt = (
            "Write a bedtime story script for a parent to edit, then speak aloud.\n"
            "Titles may say Romy. Spoken names are Rowmy, Maama, and Baaba.\n"
            "Keep square-bracket lines such as [pause] as audio direction, not spoken words.\n"
            f"Aim for about {words} spoken words, a {length} listen.\n"
            f"Title: {title}\n"
            f"Characters: {characters}\n"
            f"Points to cover / interests: {interests}\n"
            f"Story outline: {outline}\n"
            "Return only the script body."
        )
        raw = self._post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
            headers={
                "x-goog-api-key": self._api_key,
                "Content-Type": "application/json",
            },
            body=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode(),
        )
        data = json.loads(raw)
        return str(data["candidates"][0]["content"]["parts"][0]["text"]).strip()


def gemini_http_post(url: str, *, headers: dict[str, str], body: bytes) -> bytes:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request) as response:
            return response.read()
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        log.error("Gemini HTTP %s for %s: %s", err.code, url.split("?", 1)[0], detail)
        err.vendor_message = vendor_error_message(detail)
        raise
