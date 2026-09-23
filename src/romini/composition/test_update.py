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


def test_update_main_skips_when_mpv_is_playing(monkeypatch) -> None:
    from romini.composition.pi import MpvIpcStatus
    from romini.composition.update import main as update_main

    class Sock:
        def sendall(self, data: bytes) -> None:
            return

        def recv(self, n: int) -> bytes:
            return b'{"data":false,"error":"success"}\n'

        def close(self) -> None:
            return

    installed: list[str] = []

    def urlopen(request, timeout: int = 30):
        class Resp:
            def read(self) -> bytes:
                return (
                    b'{"tag_name":"v0.2.0","assets":[{"name":"romini-0.2.0-py3-none-any.whl",'
                    b'"browser_download_url":"https://example.test/romini.whl"}]}'
                )

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return Resp()

    monkeypatch.setenv("ROMINI_PIP", "/bin/false")
    monkeypatch.setattr(
        "romini.composition.update.run_cli",
        lambda **kwargs: installed.append(type(kwargs["player"]).__name__) or "skipped",
    )
    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setattr("romini.composition.pi.MpvIpcStatus", lambda: MpvIpcStatus(connect=lambda path: Sock()))

    try:
        update_main()
    except SystemExit as exc:
        assert exc.code == 0
    assert installed == ["MpvIpcStatus"]


def test_update_main_records_a_skip_in_plain_language(monkeypatch, tmp_path) -> None:
    from romini.composition.update import main as update_main
    from romini.composition.update import plain_update_status

    status = tmp_path / "update-check.json"

    def urlopen(request, timeout: int = 30):
        class Resp:
            def read(self) -> bytes:
                return (
                    b'{"tag_name":"v0.2.0","assets":[{"name":"romini-0.2.0-py3-none-any.whl",'
                    b'"browser_download_url":"https://example.test/romini.whl"}]}'
                )

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return Resp()

    monkeypatch.setenv("ROMINI_UPDATE_STATUS", str(status))
    monkeypatch.setattr("romini.composition.update.run_cli", lambda **kwargs: "skipped")
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    try:
        update_main()
    except SystemExit as exc:
        assert exc.code == 0

    spoken = plain_update_status(status)
    assert spoken.startswith("Last checked ")
    assert "skipped the install because a story was playing" in spoken
    assert "romini-update" not in spoken
    assert "systemctl" not in spoken


def test_update_restart_uses_passwordless_sudo(monkeypatch) -> None:
    from romini.composition.update import restart_player

    calls: list[list[str]] = []

    def run(cmd: list[str], check: bool = False) -> None:
        calls.append(cmd)

    monkeypatch.setattr("romini.composition.update.subprocess.run", run)
    restart_player()

    assert calls == [["sudo", "-n", "systemctl", "restart", "romini-core"]]


def test_update_main_records_the_check_when_install_fails(monkeypatch, tmp_path) -> None:
    from romini.composition.update import describe_update_center
    from romini.composition.update import main as update_main

    status = tmp_path / "update-check.json"
    status.write_text('{"when": "23 September 2026 at 16:19", "result": "current"}')

    def urlopen(request, timeout: int = 30):
        class Resp:
            def read(self) -> bytes:
                return (
                    b'{"tag_name":"v0.31.0","assets":[{"name":"romini-0.31.0-py3-none-any.whl",'
                    b'"browser_download_url":"https://example.test/romini.whl"}]}'
                )

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        return Resp()

    def fail(**kwargs: object) -> str:
        raise RuntimeError("pip install failed")

    monkeypatch.setenv("ROMINI_UPDATE_STATUS", str(status))
    monkeypatch.setattr("romini.composition.update.run_cli", fail)
    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    try:
        update_main()
    except SystemExit as exc:
        assert exc.code == 1

    center = describe_update_center(status)
    assert center["last_check"] != "23 September 2026 at 16:19"
    assert center["last_check"] != "Not yet"
    assert center["label"] == "Check failed"
    assert "did not finish" in center["detail"]
