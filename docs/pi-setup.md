# Pi setup (headless)

Copy-paste walkthrough: **[guide.md](./guide.md) §3**. Hardware why: [hardware.md](./hardware.md). Spec: [spec.md](./spec.md). Laptop: [development.md](./development.md).

Raspberry Pi OS **Lite 64-bit**. Hostname `romini` and user `pi` match `deploy/` units as shipped. Any Imager user works if you `chown` `/var/lib/romini` and rewrite `User=` / `Group=` after copying units. Dashboard: `http://<hostname>.local`.

## 0. On the bench

Pi 4B 4GB, PN532 HAT, NTAG203, **four** 16mm buttons (one with LED), powered speaker with **aux**, 16GB microSD, **≥3A USB-C PSU**, house WPA.

## 1. Flash

Imager → Lite 64-bit. Enable SSH (key), Wi-Fi, hostname `romini` (or live with `http://<hostname>.local`). User `pi` avoids editing systemd. Do not expand to fill if you will add `romini-data` before the box can be yanked.

## 2. PN532 SPI

Jumpers: I0 L, I1 H, RSTPDN D20, DIP SPI lines ON, I2C/UART OFF. Seat HAT, coil toward lid.

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

Vendor UID demo with `PN532_SPI(reset=20, cs=4)` and an NTAG203 over the coil. If no UID, fix jumpers before software.

## 3. Buttons

Power off. Halt: COM GND, NO BCM 17, LED − GND, LED + BCM 27. Vol− BCM 22, vol+ BCM 23, play BCM 24 (NO to pin, COM GND).

```bash
sudo tee -a /boot/firmware/config.txt < /tmp/romini-provision/config.txt.romini
```

`gpio-shutdown` on BCM 17 so the halt button can wake.

GPIO press handlers are tested; `run_core_ticks` currently polls **NFC and catalog only**. See [guide.md](./guide.md) §3.4.

## 4. Speaker

AV jack → powered speaker **aux**. `speaker-test -c 2` or `mpv` at low volume. Software ceiling still applies.

## 5. Disk (before yank-risk)

Bench-only breadboard may stay a single RW root with `/var/lib/romini` on it.

Before the box leaves the bench:

1. ~6GB `rootfs`, partition 3 `mkfs.ext4 -L romini-data`.
2. Append `deploy/fstab.romini-data` (`LABEL=romini-data /var/lib/romini ext4 defaults 0 2`). No `nofail` once overlay is on.
3. `install/`, `library/`, empty `catalog.yaml` (`tracks: []`).
4. Overlay filesystem in `raspi-config` **after** that mount works.
5. `systemctl enable romini-core` so 5V always starts the player.

## 6. Network

House WPA from Imager. `avahi-daemon` + `deploy/avahi/services/romini.service` for `http://<hostname>.local`. Playback does not need the internet.

```bash
sudo mkdir -p /etc/romini /var/log/romini
sudo chmod 700 /etc/romini
# PAT in /etc/romini/env (chmod 600), never in git
```

## 7. Application

`chown` the data tree to the SSH user. Install the latest Release wheel with [guide.md](./guide.md) §3.7 (`bin/install-pi`). No git working tree. If login is not `pi`, the script rewrites `User=` / `Group=`. Enable `romini-core` and `romini-update.timer`.

Env: `ROMINI_PROFILE=pi`, `ROMINI_DATA=/var/lib/romini`, `ROMINI_DASHBOARD_PORT=80`. Core unit: `AmbientCapabilities=CAP_NET_BIND_SERVICE` (port 80). OTA: `python -m romini.composition.update` in the venv.

## 8. Checks

| Symptom | Check |
|---------|--------|
| No UID | DIP/I0/I1, SPI, coil, Type A tag |
| I2C wedged | HAT not in I2C mode |
| Brown-out | PSU ≥3A |
| No sound | Aux cable, ALSA not HDMI-only, speaker powered |
| Uploads vanish | Overlay on without `romini-data` |
| Halt / no wake | BCM 17, gpio-shutdown, NO vs NC |
| Catalog ignored | `catalog.yaml` on `romini-data`, UID hex, MP3 under `library/` |
| OTA skipped | Track is playing (mpv IPC) |
| `Permission denied` on venv | Tree still root-owned |
| bind port 80 errno 13 | Missing `AmbientCapabilities` on `romini-core` |

## Files

| Doc | Role |
|------|------|
| [guide.md](./guide.md) | Step-by-step including this page |
| [hardware.md](./hardware.md) | BOM, pins |
| [architecture.md](./architecture.md) | Daemon, OTA |
| [spec.md](./spec.md) | Behaviour |
| [library-catalog.md](./library-catalog.md) | YAML drop-in |
| [development.md](./development.md) | `sim` |
