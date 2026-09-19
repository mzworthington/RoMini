from pathlib import Path

from romini.composition.provision import ensure_data_tree
from romini.fakes import FakeLed, FakePlayer


def test_ensure_data_tree_creates_library_catalog_install_and_repo(tmp_path: Path) -> None:
    root = tmp_path / "romini"
    ensure_data_tree(root)

    assert (root / "library").is_dir()
    assert (root / "install").is_dir()
    assert (root / "repo").is_dir()
    assert (root / "catalog.yaml").read_text() == "tracks: []\n"


def test_romini_data_fstab_line_has_label_and_no_nofail() -> None:
    from romini.composition.provision import ROMINI_DATA_FSTAB

    assert "LABEL=romini-data" in ROMINI_DATA_FSTAB
    assert "/var/lib/romini" in ROMINI_DATA_FSTAB
    assert "nofail" not in ROMINI_DATA_FSTAB


def test_gpio_shutdown_overlay_uses_bcm_17() -> None:
    from romini.composition.provision import GPIO_SHUTDOWN_OVERLAY

    assert "gpio-shutdown" in GPIO_SHUTDOWN_OVERLAY
    assert "gpio_pin=17" in GPIO_SHUTDOWN_OVERLAY


def test_romini_core_service_starts_on_boot() -> None:
    from romini.composition.provision import ROMINI_CORE_SERVICE

    assert "ExecStart=" in ROMINI_CORE_SERVICE
    assert "romini-core" in ROMINI_CORE_SERVICE
    assert "ROMINI_PROFILE=pi" in ROMINI_CORE_SERVICE
    assert "ROMINI_DATA=/var/lib/romini" in ROMINI_CORE_SERVICE
    assert "ROMINI_DASHBOARD_PORT=80" in ROMINI_CORE_SERVICE
    assert "WantedBy=multi-user.target" in ROMINI_CORE_SERVICE
    assert "RuntimeDirectory=romini" in ROMINI_CORE_SERVICE
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in ROMINI_CORE_SERVICE


def test_romini_update_timer_runs_installed_module() -> None:
    from romini.composition.provision import ROMINI_UPDATE_SERVICE, ROMINI_UPDATE_TIMER

    assert "OnBootSec=" in ROMINI_UPDATE_TIMER
    assert "romini-update.service" in ROMINI_UPDATE_TIMER
    assert "python -m romini.composition.update" in ROMINI_UPDATE_SERVICE
    assert "/var/lib/romini/repo" not in ROMINI_UPDATE_SERVICE
    assert "Type=oneshot" in ROMINI_UPDATE_SERVICE


def test_avahi_http_service_advertises_parent_dashboard() -> None:
    from romini.composition.provision import AVAHI_HTTP_SERVICE

    assert "_http._tcp" in AVAHI_HTTP_SERVICE
    assert "<port>80</port>" in AVAHI_HTTP_SERVICE


def test_write_provision_files_drops_units_and_fstab(tmp_path: Path) -> None:
    from romini.composition.provision import write_provision_files

    dest = tmp_path / "etc"
    write_provision_files(dest)

    assert (dest / "systemd/system/romini-core.service").is_file()
    assert (dest / "systemd/system/romini-update.service").is_file()
    assert (dest / "systemd/system/romini-update.timer").is_file()
    assert (dest / "avahi/services/romini.service").is_file()
    assert "LABEL=romini-data" in (dest / "fstab.romini-data").read_text()
    cfg = (dest / "config.txt.romini").read_text()
    assert "gpio-shutdown" in cfg
    assert "dtparam=i2c_arm=on" in cfg
    assert "dtparam=spi=on" in cfg


def test_provision_module_writes_units_from_argv(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "provision"
    monkeypatch.setattr("sys.argv", ["provision", str(dest)])
    from romini.composition.provision import main

    main()

    assert (dest / "systemd/system/romini-update.service").is_file()
    assert "python -m romini.composition.update" in (dest / "systemd/system/romini-update.service").read_text()


def test_load_sim_box_creates_data_tree_when_empty(tmp_path: Path) -> None:
    from romini.composition.sim import load_sim_box

    root = tmp_path / "romini"
    load_sim_box(data_dir=root, player=FakePlayer(), led=FakeLed())

    assert (root / "catalog.yaml").read_text() == "tracks: []\n"
    assert (root / "library").is_dir()


def test_repo_deploy_contains_romini_core_service() -> None:
    unit = Path(__file__).resolve().parents[3] / "deploy" / "systemd" / "system" / "romini-core.service"
    assert "romini-core" in unit.read_text()
    assert "WantedBy=multi-user.target" in unit.read_text()
    assert "RuntimeDirectory=romini" in unit.read_text()


def test_repo_has_a_python_lockfile() -> None:
    root = Path(__file__).resolve().parents[3]
    assert (root / "uv.lock").is_file()
