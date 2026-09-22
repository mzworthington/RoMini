from romini.features.library.shelves import file_spec, shelf_for


def test_bedtime_music_and_audiobook_paths_pick_a_shelf() -> None:
    assert shelf_for("bedtime/whale.mp3") == "bedtime"
    assert shelf_for("music/rhymes.mp3") == "music"
    assert shelf_for("audiobooks/gruffalo.flac") == "audiobooks"
    assert shelf_for("ambient/rain.ogg") == "ambient"
    assert shelf_for("stories/frog.mp3") == ""


def test_file_spec_is_the_uppercase_suffix() -> None:
    assert file_spec("stories/frog.mp3") == "MP3"
    assert file_spec("stories/frog") == ""
