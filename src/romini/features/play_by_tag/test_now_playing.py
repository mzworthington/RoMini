from datetime import datetime

from romini.features.play_by_tag.now_playing import describe_now_playing


def test_now_playing_names_the_story_figure_and_clock() -> None:
    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 22, 33)

        def position_sec(self) -> float:
            return 0.0

    view = describe_now_playing(
        Playing(),
        tracks=[
            {
                "uid": "04aabbccddeeff",
                "title": "The Frog Prince",
                "path": "stories/frog-prince.mp3",
            }
        ],
        tags=[{"uid": "04aabbccddeeff", "name": "Frog"}],
    )

    assert view is not None
    assert view.story == "The Frog Prince"
    assert view.trigger == "Frog"
    assert view.time == "22:33"
    assert view.is_playing is True


def test_now_playing_is_absent_when_the_box_is_quiet() -> None:
    class Quiet:
        def is_playing(self) -> bool:
            return False

        def playing_uid(self) -> str | None:
            return None

        def playing_path(self) -> str | None:
            return None

        def position_sec(self) -> float:
            return 0.0

    assert describe_now_playing(Quiet(), tracks=[], tags=[]) is None


def test_now_playing_falls_back_to_filename_and_uid() -> None:
    class Playing:
        def is_playing(self) -> bool:
            return True

        def playing_uid(self) -> str:
            return "04aabbccddeeff"

        def playing_path(self) -> str:
            return "stories/frog-prince.mp3"

        def started_at(self) -> datetime:
            return datetime(2026, 9, 19, 7, 5)

    view = describe_now_playing(Playing(), tracks=[], tags=[])

    assert view is not None
    assert view.story == "frog-prince.mp3"
    assert view.trigger == "04aabbccddeeff"
    assert view.time == "07:05"
