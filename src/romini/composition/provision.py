from pathlib import Path

ROMINI_DATA_FSTAB = "LABEL=romini-data /var/lib/romini ext4 defaults 0 2"
GPIO_SHUTDOWN_OVERLAY = "dtoverlay=gpio-shutdown,gpio_pin=17"
ROMINI_CORE_SERVICE = """[Unit]
Description=RoMini player
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/var/lib/romini
Environment=ROMINI_PROFILE=pi
Environment=ROMINI_DATA=/var/lib/romini
Environment=ROMINI_DASHBOARD_PORT=80
EnvironmentFile=-/etc/romini/env
RuntimeDirectory=romini
RuntimeDirectoryMode=0700
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
ExecStart=/var/lib/romini/install/venv/bin/romini-core
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
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
    (dest / "fstab.romini-data").write_text(ROMINI_DATA_FSTAB + "\n")
    (dest / "config.txt.romini").write_text(GPIO_SHUTDOWN_OVERLAY + "\n")


def main() -> None:
    import sys

    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("provision")
    write_provision_files(dest)


if __name__ == "__main__":
    main()
