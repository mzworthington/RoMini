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


def test_boot_config_blanks_hdmi_bluetooth_and_leds() -> None:
    from romini.composition.provision import merge_boot_config

    text = merge_boot_config("")

    assert "hdmi_blanking=2" in text
    assert "dtoverlay=disable-bt" in text
    assert "dtparam=act_led_trigger=none" in text
    assert "dtparam=pwr_led_trigger=none" in text


def test_gpio_shutdown_overlay_stays_off_the_i2c_clock() -> None:
    from romini.composition.provision import GPIO_SHUTDOWN_OVERLAY

    assert GPIO_SHUTDOWN_OVERLAY == "dtoverlay=gpio-shutdown,gpio_pin=17"


def test_romini_core_service_prepares_the_governor_and_wifi_sleep() -> None:
    from romini.composition.provision import ROMINI_CORE_SERVICE

    assert "ExecStartPre=+" in ROMINI_CORE_SERVICE
    assert "scaling_governor" in ROMINI_CORE_SERVICE
    assert "iw dev wlan0 set power_save on" in ROMINI_CORE_SERVICE


def test_romini_core_service_can_read_the_system_journal() -> None:
    from romini.composition.provision import ROMINI_CORE_SERVICE

    assert "SupplementaryGroups=systemd-journal" in ROMINI_CORE_SERVICE


def test_romini_core_starts_before_the_network_is_online() -> None:
    from romini.composition.provision import ROMINI_CORE_SERVICE, ROMINI_UPDATE_SERVICE

    unit = Path(__file__).resolve().parents[3] / "deploy" / "systemd" / "system" / "romini-core.service"
    assert "network-online.target" not in ROMINI_CORE_SERVICE
    assert "network-online.target" not in unit.read_text()
    assert "network-online.target" in ROMINI_UPDATE_SERVICE


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


def test_romini_core_service_lets_sudo_become_root() -> None:
    from romini.composition.provision import ROMINI_CORE_SERVICE

    assert "CapabilityBoundingSet" not in ROMINI_CORE_SERVICE


def test_provision_lets_the_updater_apply_boot_config_without_a_password(tmp_path: Path) -> None:
    from romini.composition.provision import write_provision_files

    dest = tmp_path / "etc"
    write_provision_files(dest)
    sudoers = (dest / "sudoers.d" / "romini").read_text()

    assert "NOPASSWD: /var/lib/romini/install/venv/bin/python -m romini.composition.provision --apply-boot" in sudoers


def test_provision_lets_the_dashboard_systemctl_without_a_password(tmp_path: Path) -> None:
    from romini.composition.provision import write_provision_files

    dest = tmp_path / "etc"
    write_provision_files(dest)
    sudoers = (dest / "sudoers.d" / "romini").read_text()

    assert "NOPASSWD" in sudoers
    assert "/usr/bin/systemctl restart romini-core" in sudoers
    assert "/usr/bin/systemctl start --no-block romini-update.service" in sudoers


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


def test_apply_boot_cli_exits_10_until_the_overlay_is_present(tmp_path: Path, monkeypatch) -> None:
    from romini.composition.provision import main

    path = tmp_path / "config.txt"
    path.write_text("dtparam=audio=on\n")
    monkeypatch.setattr("sys.argv", ["provision", "--apply-boot", str(path)])

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 10
    else:
        raise AssertionError("expected reboot exit")

    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0

    assert path.read_text().count("dtoverlay=audremap,pins_18_19") == 1


def test_apply_boot_config_writes_audremap_once(tmp_path: Path) -> None:
    from romini.composition.provision import apply_boot_config

    path = tmp_path / "config.txt"
    path.write_text("dtparam=audio=on\n")

    assert apply_boot_config(path) is True
    assert apply_boot_config(path) is False
    text = path.read_text()
    assert text.count("dtoverlay=audremap,pins_18_19") == 1
    assert text.count("dtparam=audio=on") == 1


def test_merge_boot_config_moves_shutdown_off_the_i2c_clock() -> None:
    from romini.composition.provision import merge_boot_config

    merged = merge_boot_config("dtoverlay=gpio-shutdown,gpio_pin=3\n")

    assert merged.count("gpio-shutdown") == 1
    assert "dtoverlay=gpio-shutdown,gpio_pin=17" in merged


def test_merge_boot_config_appends_audremap_once() -> None:
    from romini.composition.provision import merge_boot_config

    existing = "dtparam=audio=on\ndtoverlay=gpio-shutdown,gpio_pin=17\n"
    once = merge_boot_config(existing)
    twice = merge_boot_config(once)

    assert once.count("dtoverlay=audremap,pins_18_19") == 1
    assert once.count("dtparam=audio=on") == 1
    assert once.count("dtoverlay=gpio-shutdown,gpio_pin=17") == 1
    assert twice == once


def test_boot_config_disables_the_analogue_dither_that_hisses_while_idle(tmp_path: Path) -> None:
    from romini.composition.provision import apply_boot_config

    path = tmp_path / "config.txt"
    path.write_text("dtparam=audio=on\n")

    apply_boot_config(path)

    assert "disable_audio_dither=1" in path.read_text()


def test_provision_config_routes_analogue_audio_to_gpio_18_and_19(tmp_path: Path) -> None:
    from romini.composition.provision import write_provision_files

    dest = tmp_path / "etc"
    write_provision_files(dest)
    cfg = (dest / "config.txt.romini").read_text()

    assert "dtparam=audio=on" in cfg
    assert "dtoverlay=audremap,pins_18_19" in cfg


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
