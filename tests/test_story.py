"""Tests for the procedural story engine."""

from romini.story import (
    DEFAULT_THEME,
    THEMES,
    Story,
    available_themes,
    generate_story,
)


def test_generate_story_basic_shape():
    story = generate_story(hero="Romy", theme="forest", seed=1)
    assert isinstance(story, Story)
    assert story.hero == "Romy"
    assert story.theme == "forest"
    assert story.title == "Romy and the Whispering Forest"
    assert len(story.paragraphs) == 5
    assert story.moral  # a lesson is always present


def test_generation_is_deterministic_with_seed():
    a = generate_story(hero="Romy", theme="ocean", seed=42)
    b = generate_story(hero="Romy", theme="ocean", seed=42)
    assert a.to_dict() == b.to_dict()


def test_different_seeds_can_differ():
    stories = {
        generate_story(hero="Romy", theme="space", seed=s).paragraphs[1]
        for s in range(20)
    }
    # With curated word banks, 20 seeds should surface more than one variant.
    assert len(stories) > 1


def test_hero_name_appears_in_story():
    story = generate_story(hero="Luna", theme="castle", seed=3)
    assert "Luna" in story.title
    assert any("Luna" in p for p in story.paragraphs)


def test_blank_hero_defaults_to_romy():
    story = generate_story(hero="   ", theme="forest", seed=0)
    assert story.hero == "Romy"


def test_hero_name_is_trimmed_and_bounded():
    story = generate_story(hero="  A" + "b" * 100, theme="forest", seed=0)
    assert len(story.hero) <= 40


def test_unknown_theme_falls_back_to_default():
    story = generate_story(hero="Romy", theme="volcano", seed=0)
    assert story.theme == DEFAULT_THEME


def test_all_themes_generate():
    for key in THEMES:
        story = generate_story(hero="Romy", theme=key, seed=7)
        assert story.theme == key
        assert story.paragraphs


def test_available_themes_matches_catalog():
    themes = available_themes()
    assert {t["key"] for t in themes} == set(THEMES)
    for t in themes:
        assert t["label"] and t["emoji"]
