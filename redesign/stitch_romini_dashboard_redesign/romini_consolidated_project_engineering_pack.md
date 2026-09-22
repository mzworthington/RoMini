# RoMini Companion App: Consolidated Project & Engineering Pack
**Version:** 1.0.0 (Nordic Sand Build)  
**Host Application:** `romini-core` / House LAN Dashboard (`http://romini.local:8080`)  
**Target Hardware:** Raspberry Pi 4 Model B (Lite 64-bit), Waveshare 21700 UPS HAT (D), PN532 NFC Module (SPI Bus 0), HiFiBerry DAC+ Mini (I2S Master)  
**Design System:** Warm Nordic Companion (`#d97706` Amber Honey, Plus Jakarta Sans, Light Mode)

---

## 1. Executive Product Requirements Document (PRD)

### 1.1 Product Vision & Core Tenets
**RoMini** is an open-source, screen-free physical audio player crafted for young children. Children interact exclusively through tactile wooden figurines embedded with NFC tokens—placing a figure on the wooden plate instantly plays a bedtime story or nursery rhyme collection.

The **RoMini Companion Web App** is the parent-facing command center hosted locally on the home Wi-Fi network (`http://romini.local:8080`).

1. **Screen-Free Sanctity:** The child never touches a screen. The companion web app exists exclusively for parent curation, safe auditory calibration, and headless hardware telemetry.
2. **Offline-First & Resilient:** Audio playback never depends on cloud servers. Lossless tracks and audiobooks reside on the internal microSD mount (`/var/lib/romini/library`).
3. **Acoustic Safety First:** Children's developing ears are protected by a WHO-compliant 75 dB SPL software ceiling, logarithmic dial calibration, and bedtime volume decrescendo.
4. **Physical 1:1 Playback Model:** No queues, no shuffle, and no multi-chapter complexities in v1. A single figurine maps directly to a standalone story or audio bundle.

---

## 2. Architecture Decision Records (ADRs)

### ADR-001: Local-First Audio Library & MicroSD Partitioning
* **Status:** Accepted
* **Context:** Children's bedtime routines require zero-latency, fail-safe playback even if home internet drops.
* **Decision:** Mount `romini-data` partition at `/var/lib/romini/library`. Headless player engine `mpv` runs over Unix IPC socket (`/tmp/mpv.sock`).
* **Consequence:** Cloud streaming is avoided; parent uploads files directly over LAN via multi-part HTTP upload.

### ADR-002: Real-Time Proximity Daemon (WebSocket vs. HTTP Polling)
* **Status:** Accepted
* **Context:** Placing a physical wooden figure onto the PN532 sensor plate must update the parent's dashboard in under 100ms.
* **Decision:** Implement an asynchronous WebSocket daemon broadcasting events (`TAG_DETECTED`, `TAG_REMOVED`, `PLAYBACK_TICK`) alongside REST endpoints.
* **Consequence:** Eliminates wasteful HTTP polling and gives parents instant visual feedback when their child docks a figure.

### ADR-003: WHO Ear-Safe Decibel Limiter & Bedtime Decrescendo
* **Status:** Accepted
* **Context:** Toddler auditory hair cells suffer damage above 75–80 dB SPL. Physical volume potentiometers can be turned erratically by children.
* **Decision:** Enforce a hard software ceiling at 75 dB SPL mapped to ALSA DAC master gain. Provide a configurable bedtime decrescendo (-0.5 dB/min) starting at 20:30.
* **Consequence:** Guarantees acoustic safety regardless of physical knob manipulation.

### ADR-004: Read-Only LAN Network Telemetry & SSH CLI Delegation
* **Status:** Accepted
* **Context:** Changing Wi-Fi credentials via an unauthenticated LAN web server creates security risks and can isolate a headless Pi.
* **Decision:** Surface read-only network diagnostics (SSID, RSSI, mDNS hostname, IP) and provide copy-paste CLI terminal snippets (`$ sudo raspi-config` or `nmtui` over SSH).
* **Consequence:** Eliminates complex network-manager web integration while keeping parents informed.

---

## 3. Backend REST API & WebSocket Specification

### 3.1 REST API Endpoints
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/system/status` | Host telemetry (CPU temp, RAM, disk usage, UPS battery voltage/percent, uptime). |
| `GET` | `/api/player/current` | Active dock state, current track metadata, elapsed seconds, play state. |
| `POST` | `/api/player/control` | Remote transport actions (`play`, `pause`, `restart`, `seek_relative`). |
| `GET` | `/api/figures` | List all registered figurines with UIDs, titles, avatars, and linked audio. |
| `POST` | `/api/figures/register` | Enter registration mode to capture new NFC token UIDs without audio playback. |
| `POST` | `/api/figures/bind` | Bind an NFC UID to an audio file in the library. |
| `GET` | `/api/library/tracks` | Directory of stored audio tracks, durations, codecs, and binding status. |
| `POST` | `/api/library/upload` | Multipart file upload parsing ID3 tags into `/var/lib/romini/library`. |
| `GET` | `/api/audio/stream/{id}` | In-browser audio auditioning stream for parental previewing. |
| `POST` | `/api/system/updates/check`| Check GitHub Releases API for latest `romini-*.whl`. |
| `POST` | `/api/system/power` | Clean shutdown (`halt`) or reboot preventing filesystem corruption. |

### 3.2 WebSocket Event Contract (`ws://romini.local:8080/ws`)
```json
// Event: NFC Figurine Docked
{
  "event": "TAG_DETECTED",
  "payload": {
    "uid": "04:A2:8E:91",
    "figure_name": "The Gruffalo Figurine",
    "edition": "Hand-carved Oak Edition #082",
    "track_title": "The Deep Dark Wood",
    "author": "Julia Donaldson",
    "duration_sec": 320,
    "position_sec": 252,
    "state": "playing"
  }
}

// Event: Playback Tick (Every 1s)
{
  "event": "PLAYBACK_TICK",
  "payload": {
    "elapsed_sec": 253,
    "total_sec": 320,
    "volume_pct": 65,
    "decibel_spl": 71,
    "decibel_cap": 75,
    "fade_active": false
  }
}

// Event: Hardware Telemetry Heartbeat (Every 2s)
{
  "event": "HARDWARE_HEALTH",
  "payload": {
    "cpu_temp_c": 42.1,
    "cpu_load_pct": 6,
    "ram_used_mb": 612,
    "ram_total_mb": 3800,
    "battery_pct": 84,
    "battery_voltage": 4.12,
    "charging": true,
    "wifi_rssi_dbm": -52
  }
}
```

---

## 4. UI Design System Specifications (`DESIGN.md`)

```yaml
name: Warm Nordic Companion
brand_personality: Tactile, warm, calming, domestic, Scandinavian woodcraft
theme:
  color_mode: LIGHT
  font_family: Plus Jakarta Sans
  primary_color: '#d97706' # Warm Amber Honey
  surface: '#fff8f4'       # Soft Nordic Sand
  surface_container: '#faf2ed'
  surface_card: '#ffffff'
  border_color: '#e5ded9'
  text_primary: '#291807'
  text_muted: '#786b62'
  accent_green: '#15803d'  # Active status / 100% Solid
  accent_red: '#b91c1c'    # Emergency mute / Lockout
roundness: rounded-2xl (16px) for cards, rounded-xl (12px) for buttons, rounded-full for pills
```

---

## 5. UI Screen Blueprints & Reproduction Prompts

### Screen 1: Figures & Tags Studio (`SCREEN_17`)
* **Purpose:** Register physical NFC figurines, assign audio stories, and monitor the live proximity reader.
* **Key Components:**
  - Official RoMini Storybox logo in masthead with system status pills.
  - Active Dock Banner showing currently seated figurine, UID, and resume status.
  - Unassigned Figurine Queue with one-click "Assign Audio" modal trigger.
  - Figurine Card Grid with tactile wooden styling, cover art, track runtime, and last-placed timestamp.

### Screen 2: Live Player & Deck (`SCREEN_15`)
* **Purpose:** Real-time domestic auditory console and remote playback supervision.
* **Key Components:**
  - Physical NFC Dock radar graphic illustrating contact verification and UID.
  - Story Header (Single-track 1:1 playback, lossless 24-bit FLAC/MP3 badge).
  - Waveform progress scrubber and transport controls (Play/Pause, ±15s scrub, restart).
  - Rotary Knob & Decibel Guard slider with strict 75 dB toddler limiter lock.
  - Bedtime Volume Decrescendo card and Night Light Halo ring controls.

### Screen 3: Audio Library & Soundtracks (`SCREEN_13`)
* **Purpose:** Manage on-device audio files, drag-and-drop uploader, and in-browser previewing.
* **Key Components:**
  - Storage & quota meters (MicroSD free space, hours remaining, I2S DAC status).
  - Drag-and-drop audio dropzone with live sync transfer queue.
  - Filterable audio table with format badges, linked figurine tag chips, and inline action buttons.
  - Sticky In-Browser Audition Streamer bar allowing parents to test audio without sounding the child player.

### Screen 4: Hardware & System Configuration (`SCREEN_11`)
* **Purpose:** Headless Raspberry Pi 4 telemetry, power controls, and safety lockouts.
* **Key Components:**
  - Telemetry card deck: Pi 4 Quad-core CPU temp & load, PN532 SPI bus latency, HiFiBerry DAC+ Mini sample rate, Waveshare UPS battery percentage and pack voltage.
  - Parental Decibel Guard (75 dB safe limit, rotary knob logarithmic curve taper, bedtime lockout).
  - Read-only Network card: SSID, RSSI -52 dBm, mDNS hostname, and SSH raspi-config CLI snippet.
  - Active Physical Dock card with live scan count and error-free read rate.
  - Firmware & OTA Update Center querying GitHub release wheels with terminal installation ledger.

---

## 6. How to Export & Deploy

1. **Frontend Code:** Select each screen on your Stitch canvas and click the **`</>` (View Code)** or **Export** button to grab the HTML/Tailwind templates.
2. **Icons & Logos:** The authentic vector logo is embedded in the masthead using `{{DATA:IMAGE:IMAGE_2}}` (`src/romini/assets/logo.svg`).
3. **Backend Integration:** Implement the async daemon in Python (FastAPI/Starlette) following the WebSocket and REST specs above, binding `mpv` via `/tmp/mpv.sock` and PN532 via SPI Bus 0.