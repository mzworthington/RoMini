# Parent dashboard

House-LAN UI. Laptop: `./bin/sim` → [http://127.0.0.1:8080](http://127.0.0.1:8080). Pi: `http://<hostname>.local`. Walkthrough: [guide.md](./guide.md) §1.4. Contract: [spec.md](./spec.md).

Screenshots live in [`images/`](./images/).

## Home

Masthead (free space, version) and a map of the other tabs.

![Home](./images/home.png)

## Library

Upload a file or folder, assign a figure to a library track, preview audio, then Place on `sim`.

![Library](./images/library.png)

## Figures

Turn NFC register on, present a UID (sim), and name tags.

![Figures](./images/figures.png)

## Stories

Title, length, characters, outline, and script. Save / Draft script sit on this page. Filename `image.png`.

![Stories](./images/image.png)

Voice picker and Speak script (ElevenLabs). Needs a key on Settings.

![Speak](./images/ai-stories.png)

## Characters

Reusable names and history for drafts. Open a row to edit.

![Characters](./images/characters.png)

## Settings

Gemini and ElevenLabs keys (masked once set) and play mode (presence vs tap). Volume lives here too; not in this crop.

![Settings](./images/settings.png)

Audit log: last 1000 box events, newest first.

![Audit log](./images/audit.png)

## Sim harness

`sim` only. Paste a UID, put it on the plate or tap, and press box buttons without GPIO.

![Sim harness](./images/test-harness.png)
