# Introducing RoMini: The Tactile, Magic Storyteller Built for Romy

*A screen-free, figure-activated audio companion that brings physical toys to life through personalized stories and music.*

**HAYWARDS HEATH, UK — 2026** — Today marks the unveiling of RoMini, an open, screen-free smart audio player engineered specifically to celebrate Romy’s 5th birthday. Designed as an independent, tactile alternative to proprietary commercial audio systems, RoMini lets children place physical figurines on top of a bespoke wooden box to instantly trigger custom audiobooks, bedtime stories, and favourite songs.

In an age dominated by bright tablets and touchscreen interfaces, RoMini returns to tactile play. By embedding miniature NFC chips into existing toys, RoMini creates an intuitive link between physical objects and rich audio narratives. When a toy is placed on the reader, the story begins; when it is removed, playback can pause smoothly, waiting to resume exactly where the listener left off. A second play style — tap the figure, then use large buttons — can be chosen from the parent dashboard.

> "Five-year-olds shouldn't need a login, a screen, or adult supervision to explore stories," said the creator of RoMini. "RoMini gives Romy total agency over her audio world. Whether it's a favourite fairy tale, a personalised story read in a parent's voice, or upbeat songs to dance to, she just puts her toy on the box and the magic happens."

## Key Features at Launch

- **Tap-to-Play Tactile Audio:** Instant playback triggered by physical figurines and NFC tokens with sub-500ms latency.
- **Smart Resume & Debounce:** Remembers playback progress per figure; presence mode pauses on lift after a short grace.
- **Physical halt, dashboard volume:** A large 16mm halt button with LED. The first box has no vol±; parents set loudness on the local dashboard under a software ceiling. Play/pause and volume buttons can be added later.
- **Offline listening:** No internet required for playback (no ads, no tracking). Software updates, when used, come from public GitHub Releases.
- **Parent catalog:** YAML on the data volume maps figures to files; the dashboard writes the same file.
- **Yank-safe box:** Overlay filesystem plus a data partition so power loss is less likely to kill the OS; USB power back on starts the player with a light and a ready sound.

RoMini is open-source and built on Raspberry Pi. Build notes, bill of materials, and daemon source live on GitHub (public from day one).
