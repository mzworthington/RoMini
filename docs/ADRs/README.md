# Architecture decision records

Sparse MADRs for choices that are hard to reverse. Day-to-day layout lives in [architecture.md](../architecture.md).

| ADR | Decision |
|-----|----------|
| [0001](./0001-python-hexagonal-daemon.md) | Python hexagonal daemon, not Node |
| [0002](./0002-github-release-wheel-ota.md) | GitHub Release wheels + systemd timer (gpio pattern) |
| [0003](./0003-overlayfs-writable-library.md) | OverlayFS OS + persistent data volume for library, state, and venv |
| [0004](./0004-composition-root-profiles.md) | `sim` vs `pi` at composition root (not gpio `python -O`) |
| [0005](./0005-pn532-spi-analogue-audio.md) | PN532 SPI + analogue line to a powered speaker |
| [0006](./0006-presence-and-tap-play-modes.md) | `presence` vs `tap` setting (default presence) |
| [0007](./0007-yaml-catalog-sqlite-session.md) | YAML catalog import; SQLite for live state |
