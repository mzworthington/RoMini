from romini.features.power.quiet import QuietHold


class Story:
    def __init__(self, *, position: float = 12.5) -> None:
        self.playing = True
        self.uid: str | None = "04aabbccddeeff"
        self.path: str | None = "stories/frog-prince.mp3"
        self.position = position
        self.pauses = 0
        self.plays: list[tuple[str, float, str]] = []

    def is_playing(self) -> bool:
        return self.playing

    def playing_uid(self) -> str | None:
        return self.uid

    def playing_path(self) -> str | None:
        return self.path

    def position_sec(self) -> float:
        return self.position

    def pause(self) -> None:
        self.pauses += 1
        self.playing = False

    def play(self, path: str, *, position_sec: float, uid: str) -> None:
        self.plays.append((path, position_sec, uid))
        self.playing = True
        self.uid = uid
        self.path = path


def test_open_latch_pauses_only_after_the_switch_has_closed() -> None:
    player = Story()
    hold = QuietHold()

    hold.follow(open_switch=True, player=player)

    assert player.pauses == 0
    assert hold.quiet is False

    hold.follow(open_switch=False, player=player)
    hold.follow(open_switch=True, player=player)

    assert player.pauses == 1
    assert player.is_playing() is False
    assert hold.quiet is True


def test_open_latch_pauses_once_while_it_stays_open() -> None:
    player = Story()
    hold = QuietHold()
    hold.follow(open_switch=False, player=player)

    hold.follow(open_switch=True, player=player)
    hold.follow(open_switch=True, player=player)

    assert player.pauses == 1


def test_closing_the_latch_resumes_a_story_still_on_the_pad() -> None:
    player = Story()
    hold = QuietHold()
    hold.follow(open_switch=False, player=player)
    hold.follow(open_switch=True, player=player)

    hold.follow(open_switch=False, player=player)
    hold.resume(player=player, present_uid="04aabbccddeeff", require_present=True)

    assert player.plays == [("stories/frog-prince.mp3", 12.5, "04aabbccddeeff")]


def test_closing_the_latch_does_not_resume_a_lifted_presence_story() -> None:
    player = Story()
    hold = QuietHold()
    hold.follow(open_switch=False, player=player)
    hold.follow(open_switch=True, player=player)

    hold.follow(open_switch=False, player=player)
    hold.resume(player=player, present_uid=None, require_present=True)

    assert player.plays == []


def test_closing_the_latch_resumes_a_tap_story_with_no_figure() -> None:
    player = Story()
    hold = QuietHold()
    hold.follow(open_switch=False, player=player)
    hold.follow(open_switch=True, player=player)

    hold.follow(open_switch=False, player=player)
    hold.resume(player=player, present_uid=None, require_present=False)

    assert player.plays == [("stories/frog-prince.mp3", 12.5, "04aabbccddeeff")]
