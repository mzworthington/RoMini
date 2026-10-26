from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import Request
from fastapi.responses import RedirectResponse

from romini.features.library.track_facts import TrackFacts, describe_audio

_AUDIO_CACHE_LIMIT = 64
_AUDIO_FACTS: OrderedDict[tuple[str, int, int], TrackFacts] = OrderedDict()
_HIDDEN_TRACKS = "romini-hidden"


def public_https_url(storage: object, path: str) -> str:
    locate = getattr(storage, "public_url", None)
    if not callable(locate) or not path:
        return ""
    url = locate(path)
    if isinstance(url, str) and url.startswith("https://"):
        return url
    return ""


def library_paths(storage: object) -> list[str]:
    listing = getattr(storage, "paths", None)
    if not callable(listing):
        return []
    return [str(path) for path in listing()]


def stored_size(storage: object, path: str) -> int | None:
    sized = getattr(storage, "size", None)
    if callable(sized):
        value = sized(path)
        if isinstance(value, int) and value >= 0:
            return value
    files = getattr(storage, "files", None)
    if isinstance(files, dict):
        audio = files.get(path)
        if isinstance(audio, (bytes, bytearray)):
            return len(audio)
    return None


def audio_facts(storage: object, path: str) -> TrackFacts | None:
    key = _stamp_key(storage, path)
    if key is not None:
        cached = _AUDIO_FACTS.get(key)
        if cached is not None:
            _AUDIO_FACTS.move_to_end(key)
            return cached
    facts = _read_facts(storage, path)
    if facts is not None and key is not None:
        _remember_facts(key, facts)
    return facts


def hidden_track_paths(request: Request) -> set[str]:
    raw = unquote(request.cookies.get(_HIDDEN_TRACKS, ""))
    return {part for part in raw.split("\n") if part.strip() and ".." not in Path(part).parts}


def remember_hidden_track(response: RedirectResponse, request: Request, path: str) -> None:
    hidden = hidden_track_paths(request)
    hidden.add(path.strip())
    response.set_cookie(
        _HIDDEN_TRACKS,
        quote("\n".join(sorted(hidden))),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _stamp_key(storage: object, path: str) -> tuple[str, int, int] | None:
    stamp = getattr(storage, "stamp", None)
    if not callable(stamp):
        return None
    marked = stamp(path)
    if isinstance(marked, tuple) and len(marked) == 2:
        return (path, int(marked[0]), int(marked[1]))
    return None


def _read_facts(storage: object, path: str) -> TrackFacts | None:
    read = getattr(storage, "get", None)
    audio = read(path) if callable(read) else None
    if not isinstance(audio, bytes):
        return None
    return describe_audio(audio)


def _remember_facts(key: tuple[str, int, int], facts: TrackFacts) -> None:
    _AUDIO_FACTS[key] = facts
    _AUDIO_FACTS.move_to_end(key)
    while len(_AUDIO_FACTS) > _AUDIO_CACHE_LIMIT:
        _AUDIO_FACTS.popitem(last=False)
