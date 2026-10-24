from urllib.parse import urlsplit

_BLOCKED = frozenset(
    {
        "/tracks",
        "/keys",
        "/assign",
        "/register-mode",
        "/figures/cover",
        "/library/cover",
        "/system/power",
        "/system/update",
        "/backup",
        "/play-mode",
        "/safety/eject",
        "/safety/beep",
        "/safety/sleep",
        "/stories",
        "/stories/open",
        "/stories/new",
        "/stories/delete",
        "/stories/draft",
        "/stories/speak",
        "/characters",
        "/characters/open",
        "/characters/new",
    }
)


def demo_forbids(method: str, path: str) -> bool:
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return False
    clean = path.split("?", 1)[0]
    if len(clean) > 1:
        clean = clean.rstrip("/")
    if clean in _BLOCKED:
        return True
    return clean.startswith("/tags/") and clean.endswith("/name")


def demo_return_path(referer: str) -> str:
    path = urlsplit(referer.strip()).path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return "/"
    return path
