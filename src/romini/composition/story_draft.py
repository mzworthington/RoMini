import json
import logging
from collections.abc import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


class GeminiScriptDraft:
    def __init__(self, *, api_key: str, post: Callable[..., bytes]) -> None:
        self._api_key = api_key
        self._post = post

    def draft(self, *, title: str, characters: str, interests: str, outline: str) -> str:
        prompt = (
            "Write a bedtime story script for a parent to edit, then speak aloud.\n"
            "Titles may say Romy. Spoken names are Rowmy, Maama, and Baaba.\n"
            "Keep square-bracket lines such as [pause] as audio direction, not spoken words.\n"
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
        raise
