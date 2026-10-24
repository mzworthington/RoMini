def test_object_listing_exposes_audio_urls_and_refuses_the_bytes() -> None:
    from romini.adapters.cloudflare.library import library_from_objects

    library = library_from_objects(
        [
            {"key": "frog.mp3", "size": 4},
            {"key": "covers/frog.mp3/cover.png", "size": 8},
            {"key": "notes.txt", "size": 1},
        ],
        base_url="https://media.example",
    )

    assert library.paths() == ["frog.mp3"]
    assert library.public_url("frog.mp3") == "https://media.example/frog.mp3"
    assert library.size("frog.mp3") == 4
    assert library.get("frog.mp3") is None
    assert library.cover_url("frog.mp3") == "https://media.example/covers/frog.mp3/cover.png"
    assert library.free_bytes > 0
    try:
        library.put("frog.mp3", b"id3")
    except PermissionError:
        return
    raise AssertionError("demo library accepted an upload")
