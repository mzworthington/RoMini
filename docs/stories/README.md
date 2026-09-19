# Stories

This folder is **gitignored** except for this README. Scripts and MP3s stay on your machine. Add your own bedtime stories here as markdown files; they will not be committed.

Spoken scripts for Romy. Square-bracket tags (`[pause]`, `[whispers]`) are audio direction, not spoken words. Titles keep **Romy**; spoken names are **Rowmy**, **Maama**, **Baaba**.

Render MP3s with the same stem as each markdown file:

```bash
export ELEVENLABS_API_KEY='sk_…'
export ELEVENLABS_VOICE_IDS='voice-id-one,voice-id-two'
./bin/story-audio
```

Each story picks one of those voice IDs at random. Named household voices also live in `src/romini/composition/voices.yaml`. The key stays in the environment; do not commit it.
