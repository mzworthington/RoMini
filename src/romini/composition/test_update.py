from romini.composition.update import apply_update


class Playing:
    def is_playing(self) -> bool:
        return True


def test_update_skips_while_a_track_is_playing() -> None:
    installed: list[str] = []

    result = apply_update(
        player=Playing(),
        latest_version="0.2.0",
        installed_version="0.1.0",
        wheel_url="https://example.test/romini-0.2.0-py3-none-any.whl",
        install=installed.append,
        restart=lambda: None,
    )

    assert result == "skipped"
    assert installed == []


class Idle:
    def is_playing(self) -> bool:
        return False


def test_update_installs_newer_wheel_when_idle() -> None:
    installed: list[str] = []
    restarts: list[str] = []

    result = apply_update(
        player=Idle(),
        latest_version="0.2.0",
        installed_version="0.1.0",
        wheel_url="https://example.test/romini-0.2.0-py3-none-any.whl",
        install=installed.append,
        restart=lambda: restarts.append("romini-core"),
    )

    assert result == "updated"
    assert installed == ["https://example.test/romini-0.2.0-py3-none-any.whl"]
    assert restarts == ["romini-core"]


def test_update_skips_install_when_already_current() -> None:
    installed: list[str] = []

    result = apply_update(
        player=Idle(),
        latest_version="0.1.0",
        installed_version="0.1.0",
        wheel_url="https://example.test/romini-0.1.0-py3-none-any.whl",
        install=installed.append,
        restart=lambda: None,
    )

    assert result == "current"
    assert installed == []


def test_latest_release_picks_romini_wheel() -> None:
    from romini.composition.update import latest_release

    info = latest_release(
        {
            "tag_name": "v0.2.0",
            "assets": [
                {"name": "romini-0.2.0-py3-none-any.whl", "browser_download_url": "https://example.test/romini.whl"},
                {"name": "checksums.txt", "browser_download_url": "https://example.test/sums"},
            ],
        }
    )

    assert info == ("0.2.0", "https://example.test/romini.whl")


def test_update_script_runs_python_module() -> None:
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "bin" / "update"
    assert "python -m romini.composition.update" in script.read_text()


def test_update_cli_applies_github_release_when_idle() -> None:
    from romini.composition.update import run_cli

    installed: list[str] = []

    result = run_cli(
        player=Idle(),
        fetch_release=lambda: {
            "tag_name": "v0.2.0",
            "assets": [
                {"name": "romini-0.2.0-py3-none-any.whl", "browser_download_url": "https://example.test/romini.whl"},
            ],
        },
        installed_version=lambda: "0.1.0",
        install=installed.append,
        restart=lambda: None,
    )

    assert result == "updated"
    assert installed == ["https://example.test/romini.whl"]
