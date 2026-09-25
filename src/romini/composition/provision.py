from pathlib import Path

ROMINI_DATA_FSTAB = "LABEL=romini-data /var/lib/romini ext4 defaults 0 2"
GPIO_SHUTDOWN_OVERLAY = "dtoverlay=gpio-shutdown,gpio_pin=17"
I2C_ARM = "dtparam=i2c_arm=on"
SPI_ARM = "dtparam=spi=on"
ANALOGUE_AUDIO = "dtparam=audio=on"
AUDREMAP_GPIO_18_19 = "dtoverlay=audremap,pins_18_19"
HDMI_BLANKING = "hdmi_blanking=2"
DISABLE_BT = "dtoverlay=disable-bt"
ACT_LED_OFF = "dtparam=act_led_trigger=none"
PWR_LED_OFF = "dtparam=pwr_led_trigger=none"
BOOT_CONFIG_LINES = (
    GPIO_SHUTDOWN_OVERLAY,
    I2C_ARM,
    SPI_ARM,
    ANALOGUE_AUDIO,
    AUDREMAP_GPIO_18_19,
    HDMI_BLANKING,
    DISABLE_BT,
    ACT_LED_OFF,
    PWR_LED_OFF,
)


def apply_boot_config(path: Path, lines: tuple[str, ...] = BOOT_CONFIG_LINES) -> bool:
    original = path.read_text() if path.is_file() else ""
    merged = merge_boot_config(original, lines)
    if merged == original:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(merged)
    return True


def merge_boot_config(config_text: str, lines: tuple[str, ...] = BOOT_CONFIG_LINES) -> str:
    present = {line.strip() for line in config_text.splitlines() if line.strip()}
    missing = [line for line in lines if line not in present]
    if not missing:
        return config_text
    body = config_text
    if body and not body.endswith("\n"):
        body += "\n"
    return body + "\n".join(missing) + "\n"


ROMINI_CORE_SERVICE = """[Unit]
Description=RoMini player
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
SupplementaryGroups=systemd-journal
WorkingDirectory=/var/lib/romini
Environment=ROMINI_PROFILE=pi
Environment=ROMINI_DATA=/var/lib/romini
Environment=ROMINI_DASHBOARD_PORT=80
EnvironmentFile=-/etc/romini/env
RuntimeDirectory=romini
RuntimeDirectoryMode=0700
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStartPre=+/bin/sh -c 'for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do chmod a+w "$f"; done'
ExecStartPre=+/usr/sbin/iw dev wlan0 set power_save on
ExecStart=/var/lib/romini/install/venv/bin/romini-core
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
ROMINI_SUDOERS = """%sudo ALL=(root) NOPASSWD: /usr/bin/systemctl restart romini-core
%sudo ALL=(root) NOPASSWD: /usr/bin/systemctl start --no-block romini-update.service
%sudo ALL=(root) NOPASSWD: /usr/bin/systemctl reboot
%sudo ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
%sudo ALL=(root) NOPASSWD: /var/lib/romini/install/venv/bin/python -m romini.composition.provision --apply-boot
"""
ROMINI_UPDATE_SERVICE = """[Unit]
Description=RoMini GitHub Release updater
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
Group=pi
EnvironmentFile=-/etc/romini/env
ExecStart=/var/lib/romini/install/venv/bin/python -m romini.composition.update
"""
ROMINI_UPDATE_TIMER = """[Unit]
Description=RoMini update timer

[Timer]
Unit=romini-update.service
OnBootSec=5min
OnCalendar=*-*-* 03:15:00
Persistent=true

[Install]
WantedBy=timers.target
"""
AVAHI_HTTP_SERVICE = """<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">RoMini on %h</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
  </service>
</service-group>
"""


def ensure_data_tree(root: Path) -> None:
    (root / "library").mkdir(parents=True, exist_ok=True)
    (root / "install").mkdir(parents=True, exist_ok=True)
    (root / "repo").mkdir(parents=True, exist_ok=True)
    catalog = root / "catalog.yaml"
    if not catalog.exists():
        catalog.write_text("tracks: []\n")


def write_provision_files(dest: Path) -> None:
    systemd = dest / "systemd" / "system"
    systemd.mkdir(parents=True, exist_ok=True)
    (systemd / "romini-core.service").write_text(ROMINI_CORE_SERVICE)
    (systemd / "romini-update.service").write_text(ROMINI_UPDATE_SERVICE)
    (systemd / "romini-update.timer").write_text(ROMINI_UPDATE_TIMER)
    avahi = dest / "avahi" / "services"
    avahi.mkdir(parents=True, exist_ok=True)
    (avahi / "romini.service").write_text(AVAHI_HTTP_SERVICE)
    sudoers = dest / "sudoers.d"
    sudoers.mkdir(parents=True, exist_ok=True)
    (sudoers / "romini").write_text(ROMINI_SUDOERS)
    (dest / "fstab.romini-data").write_text(ROMINI_DATA_FSTAB + "\n")
    (dest / "config.txt.romini").write_text(merge_boot_config(""))


def boot_config_path() -> Path:
    firmware = Path("/boot/firmware/config.txt")
    if firmware.is_file():
        return firmware
    return Path("/boot/config.txt")


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--apply-boot":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else boot_config_path()
        raise SystemExit(10 if apply_boot_config(path) else 0)
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("provision")
    write_provision_files(dest)


if __name__ == "__main__":
    main()
