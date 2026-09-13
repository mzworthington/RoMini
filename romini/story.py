"""The magic behind RoMini: a small procedural story engine.

Stories are assembled from curated word banks using a seeded random generator,
which keeps generation deterministic (handy for tests) while still feeling
fresh. No network access or API keys are required.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class Theme:
    """A story world: its scenery, friendly faces, and little troubles."""

    key: str
    label: str
    emoji: str
    places: tuple[str, ...]
    companions: tuple[str, ...]
    treasures: tuple[str, ...]
    troubles: tuple[str, ...]


THEMES: dict[str, Theme] = {
    "forest": Theme(
        key="forest",
        label="Whispering Forest",
        emoji="🌳",
        places=(
            "a mossy glade where the sunbeams danced",
            "a hollow oak that hummed old lullabies",
            "a bridge of woven ivy over a giggling stream",
        ),
        companions=(
            "a sleepy hedgehog named Pip",
            "a firefly who spoke in tiny sparks",
            "a wise old owl with spectacles",
        ),
        treasures=(
            "a lantern that glowed with kindness",
            "an acorn that granted one gentle wish",
            "a feather that could tickle away any worry",
        ),
        troubles=(
            "the moon had misplaced its silver light",
            "the forest animals had forgotten how to laugh",
            "a grumpy fog refused to lift from the trees",
        ),
    ),
    "ocean": Theme(
        key="ocean",
        label="Sparkling Ocean",
        emoji="🌊",
        places=(
            "a coral castle that shimmered like a rainbow",
            "a cove where seashells sang duets",
            "a kelp forest swaying to a secret tune",
        ),
        companions=(
            "a giggly dolphin named Marina",
            "a shy octopus who juggled pearls",
            "a turtle who told the calmest stories",
        ),
        treasures=(
            "a pearl that remembered every good dream",
            "a conch that whispered brave ideas",
            "a starfish compass pointing toward friends",
        ),
        troubles=(
            "the tide had forgotten the way back to shore",
            "the sea creatures lost their favorite song",
            "a lonely whale could not find its family",
        ),
    ),
    "space": Theme(
        key="space",
        label="Starry Space",
        emoji="🚀",
        places=(
            "a marshmallow moon with bouncy craters",
            "a comet's tail that sprinkled stardust",
            "a planet made entirely of soft pillows",
        ),
        companions=(
            "a curious little robot named Bolt",
            "a shooting star who loved knock-knock jokes",
            "a fuzzy alien who collected giggles",
        ),
        treasures=(
            "a jar of bottled starlight",
            "a map stitched from constellations",
            "a rocket whistle that summoned brave winds",
        ),
        troubles=(
            "the stars had tangled all their twinkles",
            "the smallest planet felt terribly left out",
            "a rain of confetti clouds hid the North Star",
        ),
    ),
    "castle": Theme(
        key="castle",
        label="Cloud Castle",
        emoji="🏰",
        places=(
            "a tower spun from cotton-candy clouds",
            "a garden where the flowers hummed",
            "a drawbridge guarded by friendly gargoyles",
        ),
        companions=(
            "a dragon named Ember who breathed bubbles",
            "a knight in shining pajamas",
            "a talking teapot full of clever plans",
        ),
        treasures=(
            "a crown that sparkled with courage",
            "a key that opened doors to daydreams",
            "a quill that wrote wishes into rainbows",
        ),
        troubles=(
            "the castle bells had lost their cheerful ring",
            "the royal garden refused to bloom",
            "a mischievous breeze scattered every storybook",
        ),
    ),
}

DEFAULT_THEME = "forest"

_LESSONS = (
    "being brave often just means being kind.",
    "the biggest adventures begin with a single small step.",
    "sharing a smile can light up the darkest day.",
    "helping a friend is its own kind of magic.",
    "even the tiniest hero can do enormous good.",
)


@dataclass
class Story:
    """A finished tale, ready to be read aloud at bedtime."""

    title: str
    hero: str
    theme: str
    theme_label: str
    emoji: str
    paragraphs: list[str] = field(default_factory=list)
    moral: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def available_themes() -> list[dict[str, str]]:
    """Return theme options suitable for a UI dropdown."""

    return [
        {"key": t.key, "label": t.label, "emoji": t.emoji}
        for t in THEMES.values()
    ]


def _clean_hero(hero: str | None) -> str:
    hero = (hero or "").strip()
    if not hero:
        return "Romy"
    # Keep it short and tidy for a title; strip anything unruly.
    hero = " ".join(hero.split())
    return hero[:40]


def generate_story(
    hero: str | None = "Romy",
    theme: str | None = DEFAULT_THEME,
    seed: int | None = None,
) -> Story:
    """Weave a short, gentle story for the given ``hero`` and ``theme``.

    Passing a ``seed`` makes the output deterministic, which the tests rely on.
    """

    hero_name = _clean_hero(hero)
    theme_key = (theme or DEFAULT_THEME).strip().lower()
    world = THEMES.get(theme_key, THEMES[DEFAULT_THEME])

    rng = random.Random(seed)
    place = rng.choice(world.places)
    companion = rng.choice(world.companions)
    treasure = rng.choice(world.treasures)
    trouble = rng.choice(world.troubles)
    lesson = rng.choice(_LESSONS)

    title = f"{hero_name} and the {world.label}"

    paragraphs = [
        (
            f"Once upon a time, in {place}, lived a brave little hero named "
            f"{hero_name}. {hero_name} loved the {world.label.lower()} more than "
            f"anywhere else in the whole wide world."
        ),
        (
            f"One morning, {hero_name} discovered that {trouble}. "
            f"\u201cOh dear,\u201d said {hero_name}. \u201cSomeone has to help!\u201d "
            f"And so, with a deep breath and a big smile, the adventure began."
        ),
        (
            f"Along the way, {hero_name} met {companion}, who became a true "
            f"friend. Together they found {treasure}, and it filled their hearts "
            f"with hope."
        ),
        (
            f"With a little courage and a lot of kindness, {hero_name} set "
            f"everything right again. The {world.label.lower()} sparkled with joy, "
            f"and everyone cheered for their brave new hero."
        ),
        (
            f"That night, snuggled up warm and cozy, {hero_name} smiled and "
            f"remembered that {lesson} The End. {world.emoji}"
        ),
    ]

    return Story(
        title=title,
        hero=hero_name,
        theme=world.key,
        theme_label=world.label,
        emoji=world.emoji,
        paragraphs=paragraphs,
        moral=lesson,
    )
