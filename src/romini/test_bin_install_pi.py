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
    assert 'cd "${HOME:-/}"' in script


def test_install_pi_script_installs_pn532_hat_packages() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert "adafruit-circuitpython-pn532" in script
    assert "adafruit-blinka" in script
    assert "RPi.GPIO" in script
    assert "spidev" not in script
    assert "do_i2c 0" in script


def test_install_pi_script_installs_lgpio_build_deps() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert "swig" in script
    assert "python3-dev" in script
    assert "liblgpio-dev" in script
