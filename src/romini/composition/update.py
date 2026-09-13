from collections.abc import Callable
from typing import Protocol


class Playing(Protocol):
    def is_playing(self) -> bool: ...


def latest_release(payload: dict) -> tuple[str, str]:
    tag = str(payload["tag_name"])
    version = tag[1:] if tag.startswith("v") else tag
    for asset in payload.get("assets") or []:
        name = asset.get("name", "")
        if name.endswith(".whl") and name.startswith("romini-"):
            return version, str(asset["browser_download_url"])
    raise ValueError("no romini wheel in release")


def apply_update(
    *,
    player: Playing,
    latest_version: str,
    installed_version: str,
    wheel_url: str,
    install: Callable[[str], None],
    restart: Callable[[], None],
) -> str:
    if player.is_playing():
        return "skipped"
    if latest_version == installed_version:
        return "current"
    install(wheel_url)
    restart()
    return "updated"


def run_cli(
    *,
    player: Playing,
    fetch_release: Callable[[], dict],
    installed_version: Callable[[], str],
    install: Callable[[str], None],
    restart: Callable[[], None],
) -> str:
    latest_version, wheel_url = latest_release(fetch_release())
    return apply_update(
        player=player,
        latest_version=latest_version,
        installed_version=installed_version(),
        wheel_url=wheel_url,
        install=install,
        restart=restart,
    )


def main() -> int:
    import json
    import os
    import subprocess
    import urllib.request

    class Idle:
        def is_playing(self) -> bool:
            return False

    repo = os.environ.get("GITHUB_REPO", "mzworthington/RoMini")
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "romini-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode())

    pip = os.environ.get("ROMINI_PIP", "/var/lib/romini/install/venv/bin/pip")

    def installed_version() -> str:
        shown = subprocess.run([pip, "show", "romini"], check=False, capture_output=True, text=True)
        for line in shown.stdout.splitlines():
            if line.startswith("Version: "):
                return line.split()[1]
        return "0.0.0"

    def install(url: str) -> None:
        subprocess.run([pip, "install", "--upgrade", url], check=True)

    def restart() -> None:
        subprocess.run(["systemctl", "restart", "romini-core"], check=False)

    result = run_cli(
        player=Idle(),
        fetch_release=lambda: payload,
        installed_version=installed_version,
        install=install,
        restart=restart,
    )
    raise SystemExit(0 if result in {"updated", "current", "skipped"} else 1)


if __name__ == "__main__":
    main()
