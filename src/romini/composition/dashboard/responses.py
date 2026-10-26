from pathlib import Path
from urllib.parse import unquote, urlencode

from fastapi.responses import RedirectResponse

HOME_NOTICES = {
    "assigned": "Figure assigned",
    "retitled": "Title saved",
    "deleted": "Track deleted",
    "play-mode": "Play mode saved",
    "uploaded": "Track stored",
    "full": "Storage is full",
    "register-on": "Place a figure on the box",
    "register-off": "Register off",
    "named": "Figure named",
    "placed": "Figure placed",
    "paused": "Paused",
    "playing": "Playing",
    "stopped": "Stopped",
    "needed": "Fill in the required fields",
    "volume": "Volume saved",
    "story": "Story saved",
    "character": "Character saved",
    "character-taken": "That name is already used",
    "keys": "Keys saved",
    "drafted": "Script drafted",
    "draft-needed": "Could not write the script",
    "spoke": "Story spoken",
    "speak-needed": "Could not speak the story",
    "speak-key-id": "ElevenLabs needs the secret that starts with sk_, not the key ID",
    "muted": "Muted",
    "beep": "NFC beep saved",
    "sleep": "The box will sleep in 30 minutes",
    "sleep-off": "Bedtime cancelled",
    "power": "Power request sent",
    "image": "Cover image stored",
    "image-needed": "Choose a PNG, JPEG, GIF, or WebP image",
    "update": "Update check started",
    "backup": "Backup restored",
    "backup-needed": "Choose a RoMini backup file",
    "demo": "That control is turned off on this demo",
}

AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus"}
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


class QuietNotices:
    def tell(self, message: str) -> None:
        return


def notice(path: str, key: str, detail: str = "") -> RedirectResponse:
    params = {"notice": key}
    if detail.strip():
        params["detail"] = detail.strip()
    return RedirectResponse(f"{path}?{urlencode(params)}", status_code=303)


def dashboard_return(raw: object, fallback: str) -> str:
    text = str(raw or "").strip()
    if not text.startswith("/") or text.startswith("//") or "\\" in text or ":" in text:
        return fallback
    return text.split("?", 1)[0]


def has_required(*values: str) -> bool:
    return all(value.strip() for value in values)


def is_audio_track(filename: str) -> bool:
    name = filename.replace("\\", "/").strip()
    return bool(name) and Path(name).suffix.lower() in AUDIO_SUFFIXES


def format_free_space(n: int) -> str:
    if n < 1024:
        return f"{n} bytes free"
    size = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit} free"
    return f"{n} bytes free"


def vendor_detail(err: BaseException) -> str:
    message = getattr(err, "vendor_message", "")
    return str(message or "").strip()


def format_tag_uid(uid: str) -> str:
    text = unquote(uid.strip())
    compact = "".join(character for character in text if character not in ": -").upper()
    if len(compact) < 2 or len(compact) % 2 or any(character not in "0123456789ABCDEF" for character in compact):
        return text
    return ":".join(compact[index : index + 2] for index in range(0, len(compact), 2))


def memory_fill(memory: str) -> int | None:
    used_text, _, total_text = memory.partition("/")
    try:
        used = int(used_text.strip().split()[0])
        total = int(total_text.strip().split()[0])
    except (ValueError, IndexError):
        return None
    if total <= 0:
        return None
    return min(100, round(100 * used / total))
