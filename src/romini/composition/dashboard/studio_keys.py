import os
from pathlib import Path

DRAFT_MODEL = "Gemini 3.6 Flash"
VOICE_MODEL = "ElevenLabs v3"
STUDIO_KEY_NAMES = ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_IDS")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        if not path.is_file():
            return values
        lines = path.read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def elevenlabs_api_key(value: str) -> str:
    key = value.strip()
    parts = key.split("-")
    if len(parts) == 5 and [len(part) for part in parts] == [8, 4, 4, 4, 12]:
        return ""
    return key


def studio_keys(secrets: Path | None, box_secrets: Path | None = None) -> dict[str, str]:
    file_vals = parse_env_file(secrets) if secrets is not None else {}
    box_vals = parse_env_file(box_secrets) if box_secrets is not None else {}

    def pick(name: str) -> str:
        return (file_vals.get(name) or box_vals.get(name) or os.environ.get(name) or "").strip()

    return {name: pick(name) for name in STUDIO_KEY_NAMES}


def mask_secret(value: str) -> str:
    if len(value) < 4:
        return ""
    return f"••••{value[-4:]}"


def write_studio_keys(
    secrets: Path,
    *,
    gemini_key: str,
    elevenlabs_key: str,
    elevenlabs_voices: str,
) -> None:
    current = parse_env_file(secrets)
    if gemini_key.strip():
        current["GEMINI_API_KEY"] = gemini_key.strip()
    usable_elevenlabs = elevenlabs_api_key(elevenlabs_key)
    if usable_elevenlabs:
        current["ELEVENLABS_API_KEY"] = usable_elevenlabs
    current["ELEVENLABS_VOICE_IDS"] = elevenlabs_voices.strip()
    secrets.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{name}={current[name]}\n" for name in STUDIO_KEY_NAMES if current.get(name)]
    secrets.write_text("".join(lines))
    secrets.chmod(0o600)
