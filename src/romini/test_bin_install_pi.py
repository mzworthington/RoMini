from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_install_pi_script_installs_github_wheel_without_git_clone() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert "git clone" not in script
    assert "releases/latest" in script
    assert "romini.composition.provision" in script
    assert "python -m romini.composition.update" not in script or "install/venv" in script
    assert "BOX_USER" in script
    assert "romini-core.service" in script
