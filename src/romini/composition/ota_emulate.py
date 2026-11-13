"""Laptop/CI emulator for the Pi OTA contract: install last wheel, then upgrade."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

from romini.composition.update import apply_update

WHEEL_NAME = re.compile(r"^romini-(.+)-py3-none-any\.whl$")
LIBRARY_MARKER = "library/.ota-emulate-keep"


class Idle:
    def is_playing(self) -> bool:
        return False


def parse_wheel_version(path: Path | str) -> str:
    name = Path(path).name
    matched = WHEEL_NAME.match(name)
    if matched is None:
        raise ValueError(f"not a romini wheel: {name}")
    return matched.group(1)


def version_key(version: str) -> tuple[int | str, ...]:
    parts: list[int | str] = []
    for part in version.split("."):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return tuple(parts)


def release_wheel(payload: dict) -> tuple[str, str]:
    from romini.composition.update import latest_release

    return latest_release(payload)


def choose_baseline(
    *,
    candidate_version: str,
    releases: Sequence[tuple[str, str]],
) -> tuple[str, str]:
    """Pick the newest published wheel older than the candidate (devices leave that version)."""
    for version, url in releases:
        if version_key(version) < version_key(candidate_version):
            return version, url
    raise ValueError(
        f"no published romini wheel older than candidate {candidate_version}; "
        "set ROMINI_OTA_BASELINE_WHEEL to a previous wheel path or URL"
    )


def list_release_wheels(payloads: Sequence[dict]) -> list[tuple[str, str]]:
    wheels: list[tuple[str, str]] = []
    for payload in payloads:
        try:
            wheels.append(release_wheel(payload))
        except ValueError:
            continue
    return wheels


def pip_show_version(pip: Path | str) -> str:
    shown = subprocess.run([str(pip), "show", "romini"], check=False, capture_output=True, text=True)
    for line in shown.stdout.splitlines():
        if line.startswith("Version: "):
            return line.split()[1]
    return "0.0.0"


def create_device_venv(data_root: Path, *, python: str = sys.executable) -> Path:
    venv = data_root / "install" / "venv"
    venv.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([python, "-m", "venv", str(venv)], check=True)
    pip = venv / "bin" / "pip"
    subprocess.run([str(pip), "install", "--upgrade", "pip"], check=True)
    return venv


def install_wheel(pip: Path | str, wheel: str) -> None:
    subprocess.run([str(pip), "install", "--upgrade", wheel], check=True)


def smoke_candidate(python: Path | str) -> None:
    subprocess.run(
        [
            str(python),
            "-c",
            "import romini; import romini.composition.update; import romini.composition.provision; "
            "import romini.__main__",
        ],
        check=True,
    )
    # Do not Path.resolve(): venv/bin/python often symlinks to /usr/bin/python*.
    core = Path(python).absolute().parent / "romini-core"
    if not core.is_file():
        raise RuntimeError(f"romini-core entry point missing after upgrade: {core}")


def prove_upgrade(
    *,
    data_root: Path,
    baseline_wheel: str,
    candidate_wheel: str,
    candidate_version: str,
    python: str = sys.executable,
    install: Callable[[str], None] | None = None,
    restart: Callable[[], None] | None = None,
) -> dict[str, str]:
    data_root.mkdir(parents=True, exist_ok=True)
    marker = data_root / LIBRARY_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("keep-me\n")

    venv = create_device_venv(data_root, python=python)
    pip = venv / "bin" / "pip"
    venv_python = venv / "bin" / "python"
    install_wheel(pip, baseline_wheel)
    before = pip_show_version(pip)
    if before == "0.0.0":
        raise RuntimeError(f"baseline wheel did not install romini: {baseline_wheel}")

    restarts: list[str] = []

    def do_install(url: str) -> None:
        if install is not None:
            install(url)
            return
        install_wheel(pip, url)

    def do_restart() -> None:
        restarts.append("romini-core")
        if restart is not None:
            restart()

    result = apply_update(
        player=Idle(),
        latest_version=candidate_version,
        installed_version=before,
        wheel_url=candidate_wheel,
        install=do_install,
        restart=do_restart,
    )
    if result != "updated":
        raise RuntimeError(f"expected upgrade to install candidate, got {result!r} (from {before})")

    after = pip_show_version(pip)
    if after != candidate_version:
        raise RuntimeError(f"pip show romini is {after!r}, expected {candidate_version!r}")
    if not marker.is_file() or marker.read_text() != "keep-me\n":
        raise RuntimeError("library marker vanished during upgrade")
    smoke_candidate(venv_python)
    if restarts != ["romini-core"]:
        raise RuntimeError("upgrade did not request a romini-core restart")

    return {
        "baseline_version": before,
        "candidate_version": after,
        "result": result,
        "data_root": str(data_root),
        "marker": str(marker),
    }


def build_candidate_wheel(root: Path, dist: Path, *, python: str = sys.executable) -> Path:
    dist.mkdir(parents=True, exist_ok=True)
    for old in dist.glob("romini-*.whl"):
        old.unlink()
    subprocess.run([python, "-m", "build", "--wheel", "--outdir", str(dist)], check=True, cwd=str(root))
    wheels = sorted(dist.glob("romini-*-py3-none-any.whl"))
    if not wheels:
        raise RuntimeError(f"no romini wheel in {dist}")
    return wheels[-1]


def fetch_release_payloads(repo: str, *, token: str = "", limit: int = 10) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "romini-ota-emulate"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases?per_page={limit}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if shutil.which("gh") is None:
            raise RuntimeError(f"GitHub releases API failed ({exc.code}); set GITHUB_TOKEN or install gh") from exc
        listed = subprocess.run(
            ["gh", "api", f"repos/{repo}/releases?per_page={limit}"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(listed.stdout)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub releases payload was not a list")
    return payload


def download_wheel(url: str, dest: Path, *, repo: str = "", token: str = "") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "romini-ota-emulate"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            dest.write_bytes(response.read())
        return dest
    except urllib.error.HTTPError as exc:
        if shutil.which("gh") is None or not repo:
            raise RuntimeError(f"download failed for {url}: {exc.code}") from exc
        tag = Path(url).parts[-2] if "/download/" in url else ""
        name = Path(url).name
        if not tag:
            raise RuntimeError(f"download failed for {url}: {exc.code}") from exc
        subprocess.run(
            ["gh", "release", "download", tag, "-R", repo, "-p", name, "-D", str(dest.parent), "--clobber"],
            check=True,
        )
        return dest


def resolve_baseline_wheel(
    *,
    candidate_version: str,
    repo: str,
    token: str,
    cache: Path,
    baseline: str | None,
) -> tuple[str, str]:
    if baseline:
        if baseline.startswith("https://") or baseline.startswith("http://"):
            path = download_wheel(baseline, cache / Path(baseline).name, repo=repo, token=token)
            return parse_wheel_version(path), str(path)
        path = Path(baseline)
        return parse_wheel_version(path), str(path.resolve())

    releases = list_release_wheels(fetch_release_payloads(repo, token=token))
    version, url = choose_baseline(candidate_version=candidate_version, releases=releases)
    path = download_wheel(url, cache / Path(url).name, repo=repo, token=token)
    return version, str(path)


def ota_work_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    """Throwaway trees under var/ota-emulate — never the laptop sim's ROMINI_DATA."""
    work = Path(os.environ.get("ROMINI_OTA_WORK", root / "var" / "ota-emulate")).expanduser()
    data_root = Path(os.environ.get("ROMINI_OTA_DATA", work / "device")).expanduser()
    dist = Path(os.environ.get("ROMINI_OTA_DIST", work / "dist")).expanduser()
    cache = Path(os.environ.get("ROMINI_OTA_CACHE", work / "cache")).expanduser()
    return work, data_root, dist, cache


def reset_ota_data_root(data_root: Path, *, work: Path) -> None:
    """Wipe only paths under the OTA work tree so a exported ROMINI_DATA cannot be deleted."""
    resolved = data_root.expanduser().resolve()
    work_resolved = work.expanduser().resolve()
    try:
        resolved.relative_to(work_resolved)
    except ValueError as exc:
        raise RuntimeError(
            f"refusing to wipe {resolved}; OTA emulate data must stay under {work_resolved} "
            "(use ROMINI_OTA_DATA, not ROMINI_DATA)"
        ) from exc
    if resolved.exists():
        shutil.rmtree(resolved)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(os.environ.get("ROMINI_ROOT", Path(__file__).resolve().parents[3]))
    work, data_root, dist, cache = ota_work_paths(root)
    repo = os.environ.get("GITHUB_REPO", "mzworthington/RoMini")
    token = os.environ.get("GITHUB_TOKEN", "")
    python = os.environ.get("ROMINI_PYTHON", sys.executable)
    baseline_override = os.environ.get("ROMINI_OTA_BASELINE_WHEEL")
    candidate_override = os.environ.get("ROMINI_OTA_CANDIDATE_WHEEL")

    if args in (["-h"], ["--help"]):
        print(
            "Emulate a Pi data tree: install the last older Release wheel, then upgrade to a candidate.\n"
            "Env: ROMINI_OTA_BASELINE_WHEEL, ROMINI_OTA_CANDIDATE_WHEEL, ROMINI_OTA_DATA, "
            "GITHUB_TOKEN, GITHUB_REPO\n"
            "Does not read or wipe ROMINI_DATA (laptop sim library)."
        )
        return 0

    if candidate_override:
        candidate = Path(candidate_override)
    else:
        candidate = build_candidate_wheel(root, dist, python=python)
    candidate_version = parse_wheel_version(candidate)
    baseline_version, baseline_wheel = resolve_baseline_wheel(
        candidate_version=candidate_version,
        repo=repo,
        token=token,
        cache=cache,
        baseline=baseline_override,
    )
    print(f"baseline: {baseline_version} ({baseline_wheel})")
    print(f"candidate: {candidate_version} ({candidate})")

    reset_ota_data_root(data_root, work=work)
    report = prove_upgrade(
        data_root=data_root,
        baseline_wheel=baseline_wheel,
        candidate_wheel=str(candidate.resolve()),
        candidate_version=candidate_version,
        python=python,
    )
    print(json.dumps(report, indent=2))
    print("ota emulate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
