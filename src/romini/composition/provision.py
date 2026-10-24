import os
import subprocess
import tempfile
from pathlib import Path

ROMINI_DATA_FSTAB = "LABEL=romini-data /var/lib/romini ext4 defaults 0 2"
I2C_ARM = "dtparam=i2c_arm=on"
SPI_ARM = "dtparam=spi=on"
ANALOGUE_AUDIO = "dtparam=audio=on"
DISABLE_AUDIO_DITHER = "disable_audio_dither=1"
AUDREMAP_GPIO_18_19 = "dtoverlay=audremap,pins_18_19"
HDMI_BLANKING = "hdmi_blanking=2"
DISABLE_BT = "dtoverlay=disable-bt"
ACT_LED_OFF = "dtparam=act_led_trigger=none"
PWR_LED_OFF = "dtparam=pwr_led_trigger=none"
GPIO_SHUTDOWN = "dtoverlay=gpio-shutdown,gpio_pin=26"
INITIAL_TURBO = "initial_turbo=30"
BOOT_CONFIG_LINES = (
    I2C_ARM,
    SPI_ARM,
    ANALOGUE_AUDIO,
    DISABLE_AUDIO_DITHER,
    AUDREMAP_GPIO_18_19,
    HDMI_BLANKING,
    DISABLE_BT,
    ACT_LED_OFF,
    PWR_LED_OFF,
    INITIAL_TURBO,
    GPIO_SHUTDOWN,
)


def confined_path(candidate: Path) -> Path:
    root = Path.cwd().resolve()
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if target.is_relative_to(root):
        return target
    temp = Path(tempfile.gettempdir()).resolve()
    if target.is_relative_to(temp):
        return target
    boot = Path("/boot").resolve()
    if target.is_relative_to(boot):
        return target
    raise ValueError(f"refusing to touch {target}")


def apply_boot_config(path: Path, lines: tuple[str, ...] = BOOT_CONFIG_LINES) -> bool:
    root = Path.cwd().resolve()
    candidate = path if path.is_absolute() else root / path
    normalized = os.path.realpath(candidate)
    temp_root = os.path.realpath(tempfile.gettempdir())
    boot_files = {
        os.path.realpath("/boot/config.txt"),
        os.path.realpath("/boot/firmware/config.txt"),
    }
    inside_temp = normalized.startswith(temp_root + os.sep)
    if os.path.basename(normalized) != "config.txt" or not (inside_temp or normalized in boot_files):
        raise ValueError(f"refusing to touch {normalized}")
    target = Path(normalized)
    original = target.read_text() if target.is_file() else ""
    merged = merge_boot_config(original, lines)
    if merged == original:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(merged)
    return True


def merge_boot_config(config_text: str, lines: tuple[str, ...] = BOOT_CONFIG_LINES) -> str:
    kept = [line for line in config_text.splitlines() if not line.strip().startswith("dtoverlay=gpio-shutdown")]
    body = "\n".join(kept)
    if body:
        body += "\n"
    present = {line.strip() for line in body.splitlines() if line.strip()}
    missing = [line for line in lines if line not in present]
    if not missing:
        return body
    return body + "\n".join(missing) + "\n"


ROMINI_CORE_SERVICE = """[Unit]
Description=RoMini player

[Service]
Type=simple
User=pi
Group=pi
SupplementaryGroups=systemd-journal gpio
WorkingDirectory=/var/lib/romini
Environment=ROMINI_PROFILE=pi
Environment=ROMINI_DATA=/var/lib/romini
Environment=ROMINI_DASHBOARD_PORT=80
EnvironmentFile=-/etc/romini/env
RuntimeDirectory=romini
RuntimeDirectoryMode=0700
AmbientCapabilities=CAP_NET_BIND_SERVICE
ExecStartPre=+/bin/sh -c 'for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do chmod a+w "$f"; done'
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
%sudo ALL=(root) NOPASSWD: /usr/sbin/iw dev wlan0 set power_save off
%sudo ALL=(root) NOPASSWD: /var/lib/romini/install/venv/bin/python -m romini.composition.provision --apply-boot
"""
WIFI_POWERSAVE_OFF = """[connection]
wifi.powersave = disable
"""
ROMINI_BOOT_CHIME_SERVICE = """[Unit]
Description=RoMini boot chirp
After=sound.target
Before=romini-core.service

[Service]
Type=oneshot
ExecStart=/var/lib/romini/install/venv/bin/python -m romini.features.boot.chime

[Install]
WantedBy=sound.target
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
ROMINI_STATUS_SERVICE = """[Unit]
Description=Write RoMini status onto the boot partition

[Service]
Type=oneshot
ExecStart=/bin/sh /usr/local/lib/romini/romini-status.sh
"""
ROMINI_STATUS_TIMER = """[Unit]
Description=RoMini boot-partition status note

[Timer]
OnBootSec=15s
OnUnitActiveSec=1min
Unit=romini-status.service

[Install]
WantedBy=timers.target
"""
ROMINI_STATUS_SCRIPT = """#!/bin/sh
BOOT="/boot/firmware/romini-status.txt"
if [ ! -d /boot/firmware ]; then
  BOOT="/boot/romini-status.txt"
fi
{
  date -Is
  echo "--- addr ---"
  ip -br addr
  echo "--- wifi ---"
  iw dev wlan0 link
  echo "--- units ---"
  for unit in romini-core.service avahi-daemon.service rpi-connect.service; do
    printf '%s %s\\n' "$unit" "$(systemctl is-active "$unit" 2>/dev/null || true)"
  done
  echo "--- journal ---"
  journalctl -b -n 40 --no-pager -o short-iso
} > "$BOOT" 2>&1
sync
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
    dest = confined_path(dest)
    systemd = dest / "systemd" / "system"
    systemd.mkdir(parents=True, exist_ok=True)
    (systemd / "romini-core.service").write_text(ROMINI_CORE_SERVICE)
    (systemd / "romini-boot-chime.service").write_text(ROMINI_BOOT_CHIME_SERVICE)
    (systemd / "romini-update.service").write_text(ROMINI_UPDATE_SERVICE)
    (systemd / "romini-update.timer").write_text(ROMINI_UPDATE_TIMER)
    (systemd / "romini-status.service").write_text(ROMINI_STATUS_SERVICE)
    (systemd / "romini-status.timer").write_text(ROMINI_STATUS_TIMER)
    (dest / "romini-status.sh").write_text(ROMINI_STATUS_SCRIPT)
    avahi = dest / "avahi" / "services"
    avahi.mkdir(parents=True, exist_ok=True)
    (avahi / "romini.service").write_text(AVAHI_HTTP_SERVICE)
    nm = dest / "NetworkManager" / "conf.d"
    nm.mkdir(parents=True, exist_ok=True)
    (nm / "romini-wifi.conf").write_text(WIFI_POWERSAVE_OFF)
    sudoers = dest / "sudoers.d"
    sudoers.mkdir(parents=True, exist_ok=True)
    (sudoers / "romini").write_text(ROMINI_SUDOERS)
    (dest / "fstab.romini-data").write_text(ROMINI_DATA_FSTAB + "\n")
    (dest / "config.txt.romini").write_text(merge_boot_config(""))


def grant_gpio_to_player(unit_text: str) -> str:
    granted = "SupplementaryGroups=systemd-journal gpio"
    if granted in unit_text:
        return unit_text
    return unit_text.replace("SupplementaryGroups=systemd-journal", granted, 1)


def ensure_boot_chime(directory: Path = Path("/etc/systemd/system")) -> bool:
    if not (directory / "romini-core.service").is_file():
        return False
    path = directory / "romini-boot-chime.service"
    if path.is_file() and path.read_text() == ROMINI_BOOT_CHIME_SERVICE:
        return False
    path.write_text(ROMINI_BOOT_CHIME_SERVICE)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "romini-boot-chime.service"], check=False)
    return True


def lan_root_is_the_box(root: Path) -> bool:
    return root == Path("/")


def ensure_dashboard_lan(root: Path = Path("/")) -> None:
    sudoers = root / "etc/sudoers.d/romini"
    sudoers.parent.mkdir(parents=True, exist_ok=True)
    if not sudoers.is_file() or sudoers.read_text() != ROMINI_SUDOERS:
        sudoers.write_text(ROMINI_SUDOERS)
        sudoers.chmod(0o440)
    nm = root / "etc/NetworkManager/conf.d/romini-wifi.conf"
    nm.parent.mkdir(parents=True, exist_ok=True)
    if nm.is_file() and nm.read_text() == WIFI_POWERSAVE_OFF:
        return
    nm.write_text(WIFI_POWERSAVE_OFF)
    if lan_root_is_the_box(root):
        try:
            subprocess.run(["nmcli", "general", "reload"], check=False)
        except OSError:
            return


def ensure_player_gpio(path: Path = Path("/etc/systemd/system/romini-core.service")) -> bool:
    if not path.is_file():
        return False
    original = path.read_text()
    updated = grant_gpio_to_player(original)
    if updated == original:
        return False
    path.write_text(updated)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "restart", "romini-core"], check=False)
    return True


def boot_config_path() -> Path:
    firmware = Path("/boot/firmware/config.txt")
    if firmware.is_file():
        return firmware
    return Path("/boot/config.txt")


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--apply-boot":
        if len(sys.argv) > 2:
            raise ValueError("refusing a boot config path from the command line")
        ensure_dashboard_lan()
        ensure_player_gpio()
        ensure_boot_chime()
        raise SystemExit(10 if apply_boot_config(boot_config_path()) else 0)
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("provision")
    write_provision_files(dest)


if __name__ == "__main__":
    main()
