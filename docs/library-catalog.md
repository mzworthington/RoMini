# Library catalog (YAML)

Source of truth for **Tracks and Tag mappings**. Live playback position, volume, and Play mode stay in SQLite ([ADR-0007](./ADRs/0007-yaml-catalog-sqlite-session.md)).

Path on the box: `/var/lib/romini/catalog.yaml` (data volume). Audio files sit beside it under `/var/lib/romini/library/`. `path` is relative to `library/`.

`romini-core` does this today:

1. Read `catalog.yaml` at start (`load_sim_box`).
2. Watch for changes (mtime) on the core tick loop and import again without a restart.
3. Upsert Library + TagMapping in SQLite.
4. Skip a row if the YAML is invalid or the MP3 is missing; keep playing other Tags.
5. **Not** copy pause position into YAML.
6. Unmap any UID that disappeared from the file (leave unused position rows).

Ready earcon is **not** a catalog Track; it ships in the software wheel.

Parent dashboard assign/upload updates this file, then imports, so the SD copy remains the mapping you can edit on a laptop.

```yaml
# /var/lib/romini/catalog.yaml
tracks:
  - uid: "04aabbccddeeff"   # NTAG203 UID, lowercase hex, no separators
    path: "stories/frog-prince.mp3"
    title: "The Frog Prince"
    artist: null              # optional
```

UID must be unique. A second row with the same `uid` is rejected.

On a laptop `sim` profile, the same file lives under `$ROMINI_DATA/catalog.yaml`.
