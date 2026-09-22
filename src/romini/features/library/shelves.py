from pathlib import Path


def shelf_for(path: str) -> str:
    folded = path.replace("\\", "/").lower()
    if "audiobook" in folded or "/books/" in folded or folded.startswith("books/"):
        return "audiobooks"
    if "ambient" in folded or "white-noise" in folded or "noise" in folded:
        return "ambient"
    if "music" in folded or "rhyme" in folded:
        return "music"
    if "bedtime" in folded:
        return "bedtime"
    return ""


def file_spec(path: str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix.upper()
