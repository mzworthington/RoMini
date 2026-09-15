# Local development and emulation

Step-by-step (laptop daemon, sim injectors, Pi): **[guide.md](./guide.md)**. Runtime choice: [ADR-0004](./ADRs/0004-composition-root-profiles.md). Product: [PRD_001.md](./PRD_001.md). Device layout: [architecture.md](./architecture.md).

gpio-build-monitor swaps `RPi.GPIO` for `Mock.GPIO` when `__debug__` is set (`python` vs `python -O`). RoMini does **not**. Too many peripherals, and `-O` also disables asserts. The composition root binds a **profile**.

## Profiles

| Profile | Where | Adapters |
|---------|--------|----------|
| `sim` | Laptop, CI | `FakeNfc`, silent player, `LoggingHalt`, SQLite + YAML under `$ROMINI_DATA` |
| `pi` | Box / breadboard | PN532 SPI (or FakeNfc if `nfc` missing), `MpvPlayer`, `SystemdHalt`, GPIO LED, dashboard `0.0.0.0` |

Default on a checkout: `sim`. systemd on the device: `pi`. Never detect “am I a Pi?” inside domain code.

## Inner loop

```bash
./bin/bootstrap   # venv, ruff, pytest, pre-commit, commit-msg
make test         # ruff check + format --check, pytest
```

Python is formatted with **ruff format**. GitHub YAML/JSON use Prettier via pre-commit. Hooks: ruff + Prettier on commit; pytest on **pre-push** (full suite); conventional subjects on **commit-msg**.

1. Red-green domain and slice tests with fakes (TDD guard). Catalog case: `src/romini/features/play_by_tag/`.
2. `ROMINI_PROFILE=sim ROMINI_DATA=./var/romini .venv/bin/romini-core` — TTY injectors on stdin ([guide.md](./guide.md) §1.3).
3. Dashboard + sim HTTP: `./bin/sim` (ports 8080 / 8081, stdin closed).
4. Breadboard: same binary, `ROMINI_PROFILE=pi` — [guide.md](./guide.md) §3.

## Sim injectors

`sim` only (`start_sim_http` refuses `pi` and non-localhost):

- TTY: `place`, `lift`/`remove`, `vol up`/`down`, `play`, `play long`, `halt`, `quit`
- HTTP: `POST /place/<uid>`, `/remove`, `/vol/up`, `/vol/down`, `/play`, `/halt`

Halt logs instead of `systemctl poweroff`.

## Audio on a laptop

- **Tests:** `FakePlayer` records play/pause/seek; no mpv.
- **Console `sim`:** `SilentPlayer` (no speakers). Missing mpv is not a test failure.
- **Pi / breadboard:** `MpvPlayer` via `Popen` (`--ao=alsa`, `--volume=` from the Mixer, IPC `/tmp/romini-mpv.sock`).

## CI

Same as `sim` with fakes. No QEMU job in v1.

## Explicitly out of scope for emulation

- QEMU Raspberry Pi as the daily driver.
- Importing `RPi.GPIO` behind `python -O`.
- Running OverlayFS in Docker to “feel like” the SD card.
- Shipping sim HTTP on the child’s box.
