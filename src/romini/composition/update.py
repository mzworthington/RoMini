import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
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


def describe_update_center(path: Path | None, *, channel: str = "mzworthington/RoMini") -> dict[str, str]:
    detail = plain_update_status(path)
    label = "Not checked yet"
    tone = "idle"
    last_check = "Not yet"
    if path is not None and path.is_file():
        record = json.loads(path.read_text())
        when = str(record.get("when") or "").strip()
        result = str(record.get("result") or "")
        labels = {
            "current": ("Up to date", "ok"),
            "skipped": ("Story was playing", "warn"),
            "updated": ("Installed", "ok"),
            "failed": ("Check failed", "warn"),
            "checking": ("Checking", "idle"),
        }
        if when and result in labels and detail.startswith("Last checked"):
            label, tone = labels[result]
            last_check = when
    return {
        "label": label,
        "tone": tone,
        "last_check": last_check,
        "detail": detail,
        "channel": channel,
    }


def plain_update_status(path: Path | None) -> str:
    if path is None or not path.is_file():
        return "The box has not checked for an update yet."
    record = json.loads(path.read_text())
    when = str(record.get("when") or "").strip()
    phrase = {
        "skipped": "It skipped the install because a story was playing.",
        "current": "The player is already up to date.",
        "updated": "It installed a newer player.",
        "failed": "The update did not finish.",
        "checking": "A check is running.",
    }.get(str(record.get("result") or ""))
    if not when or phrase is None:
        return "The box has not checked for an update yet."
    return f"Last checked {when}. {phrase}"


def record_update_check(path: Path, result: str, when: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    spoken = f"{when.day} {when.strftime('%B %Y at %H:%M')}"
    path.write_text(json.dumps({"when": spoken, "result": result}))


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


def boot_follow_up(result: str, *, boot_changed: bool, reboot: Callable[[], None]) -> None:
    if result in {"current", "updated"} and boot_changed:
        reboot()


def restart_player() -> None:
    subprocess.run(["sudo", "-n", "systemctl", "restart", "romini-core"], check=False)


def main() -> int:
    import json
    import os
    import traceback
    import urllib.request

    from romini.composition.pi import MpvIpcStatus

    root = Path(os.environ.get("ROMINI_DATA", "/var/lib/romini"))
    configured = os.environ.get("ROMINI_UPDATE_STATUS")
    status = Path(configured) if configured else root / "update-check.json"
    result = "failed"
    try:
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
            restart_player()

        result = run_cli(
            player=MpvIpcStatus(),
            fetch_release=lambda: payload,
            installed_version=installed_version,
            install=install,
            restart=restart,
        )
        if result in {"current", "updated"}:
            applied = subprocess.run(
                [
                    "sudo",
                    "-n",
                    "/var/lib/romini/install/venv/bin/python",
                    "-m",
                    "romini.composition.provision",
                    "--apply-boot",
                ],
                check=False,
            )
            boot_follow_up(
                result,
                boot_changed=applied.returncode == 10,
                reboot=lambda: subprocess.run(["sudo", "-n", "systemctl", "reboot"], check=False),
            )
    except Exception:
        traceback.print_exc()
        result = "failed"
    if status.parent.is_dir():
        record_update_check(status, result, datetime.now())
    raise SystemExit(0 if result in {"updated", "current", "skipped"} else 1)


if __name__ == "__main__":
    main()
