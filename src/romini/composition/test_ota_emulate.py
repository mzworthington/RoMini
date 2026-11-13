from pathlib import Path

import pytest

from romini.composition.ota_emulate import (
    choose_baseline,
    list_release_wheels,
    parse_wheel_version,
    prove_upgrade,
    version_key,
)

ROOT = Path(__file__).resolve().parents[3]


def test_parse_wheel_version_reads_romini_name() -> None:
    assert parse_wheel_version("romini-0.75.0-py3-none-any.whl") == "0.75.0"
    assert parse_wheel_version(Path("/tmp/romini-0.76.0-py3-none-any.whl")) == "0.76.0"


def test_parse_wheel_version_rejects_other_assets() -> None:
    with pytest.raises(ValueError, match="not a romini wheel"):
        parse_wheel_version("checksums.txt")


def test_version_key_orders_semver_like_tags() -> None:
    assert version_key("0.75.0") < version_key("0.76.0")
    assert version_key("0.72.3") < version_key("0.73.0")


def test_choose_baseline_picks_newest_older_release() -> None:
    baseline = choose_baseline(
        candidate_version="0.76.0",
        releases=[
            ("0.76.0", "https://example.test/romini-0.76.0-py3-none-any.whl"),
            ("0.75.0", "https://example.test/romini-0.75.0-py3-none-any.whl"),
            ("0.74.0", "https://example.test/romini-0.74.0-py3-none-any.whl"),
        ],
    )
    assert baseline == ("0.75.0", "https://example.test/romini-0.75.0-py3-none-any.whl")


def test_choose_baseline_uses_latest_when_candidate_is_newer() -> None:
    baseline = choose_baseline(
        candidate_version="0.77.0",
        releases=[
            ("0.76.0", "https://example.test/romini-0.76.0-py3-none-any.whl"),
            ("0.75.0", "https://example.test/romini-0.75.0-py3-none-any.whl"),
        ],
    )
    assert baseline == ("0.76.0", "https://example.test/romini-0.76.0-py3-none-any.whl")


def test_choose_baseline_errors_when_nothing_is_older() -> None:
    with pytest.raises(ValueError, match="no published romini wheel older"):
        choose_baseline(
            candidate_version="0.1.0",
            releases=[("0.2.0", "https://example.test/romini-0.2.0-py3-none-any.whl")],
        )


def test_list_release_wheels_skips_releases_without_romini_wheel() -> None:
    wheels = list_release_wheels(
        [
            {
                "tag_name": "v0.2.0",
                "assets": [
                    {
                        "name": "romini-0.2.0-py3-none-any.whl",
                        "browser_download_url": "https://example.test/romini.whl",
                    }
                ],
            },
            {"tag_name": "v0.1.0", "assets": [{"name": "notes.txt", "browser_download_url": "https://x"}]},
        ]
    )
    assert wheels == [("0.2.0", "https://example.test/romini.whl")]


def test_prove_upgrade_installs_candidate_over_baseline_and_keeps_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: list[str] = []
    data = tmp_path / "romini"
    state = {"version": "0.75.0"}

    def fake_create(data_root: Path, *, python: str = "") -> Path:
        venv = data_root / "install" / "venv"
        (venv / "bin").mkdir(parents=True)
        for name in ("pip", "python", "romini-core"):
            path = venv / "bin" / name
            path.write_text("#!/bin/true\n")
            path.chmod(0o755)
        return venv

    def fake_install_wheel(pip: Path | str, wheel: str) -> None:
        installed.append(wheel)
        state["version"] = "0.76.0" if "0.76.0" in wheel else "0.75.0"

    monkeypatch.setattr("romini.composition.ota_emulate.create_device_venv", fake_create)
    monkeypatch.setattr("romini.composition.ota_emulate.install_wheel", fake_install_wheel)
    monkeypatch.setattr("romini.composition.ota_emulate.pip_show_version", lambda pip: state["version"])
    monkeypatch.setattr("romini.composition.ota_emulate.smoke_candidate", lambda python: None)

    report = prove_upgrade(
        data_root=data,
        baseline_wheel="/tmp/romini-0.75.0-py3-none-any.whl",
        candidate_wheel="/tmp/romini-0.76.0-py3-none-any.whl",
        candidate_version="0.76.0",
    )

    assert report["baseline_version"] == "0.75.0"
    assert report["candidate_version"] == "0.76.0"
    assert report["result"] == "updated"
    assert (data / "library" / ".ota-emulate-keep").read_text() == "keep-me\n"
    assert any("0.75.0" in item for item in installed)
    assert any("0.76.0" in item for item in installed)


def test_ota_emulate_script_points_at_the_module() -> None:
    script = ROOT / "bin" / "ota-emulate"
    text = script.read_text()
    assert "-m romini.composition.ota_emulate" in text
    assert script.stat().st_mode & 0o111


def test_ci_runs_ota_upgrade_before_release() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "ota-upgrade:" in workflow
    assert "bin/ota-emulate" in workflow
    assert "needs: [verify, ota-upgrade]" in workflow
