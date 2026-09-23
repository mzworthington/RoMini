from romini.features.stories.cover import COVER_LIMIT, image_file_info, with_track_image

PNG = b"\x89PNG\r\n\x1a\n" + b"IHDR" + b"\x00" * 8


def test_image_file_info_names_a_png_on_the_box() -> None:
    info = image_file_info(PNG)

    assert info == {"file": "cover.png", "size": len(PNG), "media_type": "image/png"}


def test_image_file_info_names_jpeg_gif_and_webp() -> None:
    jpeg = image_file_info(b"\xff\xd8\xff\xe0" + b"\x00" * 8)
    gif = image_file_info(b"GIF89a" + b"\x00" * 8)
    webp = image_file_info(b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 4)

    assert jpeg is not None and jpeg["file"] == "cover.jpg" and jpeg["media_type"] == "image/jpeg"
    assert gif is not None and gif["file"] == "cover.gif"
    assert webp is not None and webp["file"] == "cover.webp" and webp["media_type"] == "image/webp"


def test_image_file_info_rejects_a_file_that_is_not_an_image() -> None:
    assert image_file_info(b"<html>not a picture</html>") is None
    assert image_file_info(b"") is None


def test_image_file_info_rejects_an_image_over_the_box_limit() -> None:
    assert image_file_info(b"\x89PNG\r\n\x1a\n" + b"\x00" * COVER_LIMIT) is None


def test_with_track_image_attaches_file_info_to_the_matching_track() -> None:
    catalog = 'tracks:\n  - uid: "04"\n    path: "station.mp3"\n    title: "Station"\n    artist:\n'

    updated = with_track_image(
        catalog,
        paths={"station.mp3"},
        story="the-little-station",
        info={"file": "cover.png", "size": 12, "media_type": "image/png"},
    )

    assert "file: cover.png" in updated
    assert "media_type: image/png" in updated
    assert "story: the-little-station" in updated
    assert "size: 12" in updated


def test_with_track_image_leaves_other_tracks_alone() -> None:
    catalog = "tracks:\n  - path: other.mp3\n    title: Other\n"

    assert (
        with_track_image(
            catalog,
            paths={"station.mp3"},
            story="the-little-station",
            info={"file": "cover.png", "size": 12, "media_type": "image/png"},
        )
        == catalog
    )
