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
    assert "do_spi 0" in script


def test_install_pi_script_installs_ups_hat_smbus() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert "smbus2" in script


def test_install_pi_script_installs_lgpio_build_deps() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert "swig" in script
    assert "python3-dev" in script
    assert "liblgpio-dev" in script


def test_install_pi_script_prints_bold_colour_success_when_finished() -> None:
    script = (ROOT / "bin" / "install-pi").read_text()
    assert r"\033[1;32m" in script
    assert "install complete" in script.lower()
    assert "nothing left" in script.lower()


def test_readme_walks_pi_setup_to_release_wheel_curl() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "## Set up the Pi" in readme
    assert "Raspberry Pi Imager" in readme
    assert "Lite 64-bit" in readme
    assert "curl -fsSL https://raw.githubusercontent.com/mzworthington/RoMini/main/bin/install-pi | bash" in readme
    assert "ssh pi@romini.local" in readme
    assert "http://romini.local" in readme
    assert "git clone" not in readme
    assert "pip install -e" not in readme


def test_readme_documents_forcing_pi_ota() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "sudo systemctl start romini-update.service" in readme
    assert "python -m romini.composition.update" in readme
    assert "skips while" in readme.lower() or "skip while" in readme.lower()
    assert "git pull" not in readme or "Do not `git pull`" in readme
    assert "releases/latest" in readme.lower() or "GitHub Release" in readme
