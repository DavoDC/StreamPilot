"""Tests for stream_meta.py - pure title/tag builders."""

from stream_meta import build_title, build_tags


# --- build_title ---

def test_build_title_default_template():
    title = build_title("Marvel Rivals", {}, {})
    assert title == "Davo plays Marvel Rivals!"


def test_build_title_custom_template():
    twitch_cfg = {"title_template": "Now streaming {game} - come say hi!"}
    title = build_title("Dead by Daylight", {}, twitch_cfg)
    assert title == "Now streaming Dead by Daylight - come say hi!"


def test_build_title_per_game_override_wins():
    game_cfg = {"title": "Custom Marvel Rivals Title"}
    twitch_cfg = {"title_template": "Davo plays {game}!"}
    title = build_title("Marvel Rivals", game_cfg, twitch_cfg)
    assert title == "Custom Marvel Rivals Title"


def test_build_title_empty_override_falls_back_to_template():
    game_cfg = {"title": ""}
    title = build_title("Marvel Rivals", game_cfg, {})
    assert title == "Davo plays Marvel Rivals!"


def test_build_title_truncated_to_140_chars():
    twitch_cfg = {"title_template": "X" * 200 + "{game}"}
    title = build_title("Game", {}, twitch_cfg)
    assert len(title) == 140


def test_build_title_no_twitch_cfg_uses_default():
    title = build_title("Minecraft", {}, {})
    assert title == "Davo plays Minecraft!"


# --- build_tags ---

def test_build_tags_base_and_game_combined():
    twitch_cfg = {"base_tags": ["English", "Australia"]}
    game_cfg = {"tags": ["MarvelRivals", "Rivals"]}
    tags = build_tags(game_cfg, twitch_cfg)
    assert tags == ["English", "Australia", "MarvelRivals", "Rivals"]


def test_build_tags_no_config_returns_empty():
    assert build_tags({}, {}) == []


def test_build_tags_sanitizes_special_chars_and_spaces():
    twitch_cfg = {"base_tags": ["English (AU)", "Dead by Daylight!"]}
    tags = build_tags({}, twitch_cfg)
    assert tags == ["EnglishAU", "DeadbyDaylight"]


def test_build_tags_drops_empty_after_sanitizing():
    twitch_cfg = {"base_tags": ["!!!", "English"]}
    tags = build_tags({}, twitch_cfg)
    assert tags == ["English"]


def test_build_tags_caps_length_at_25_chars():
    twitch_cfg = {"base_tags": ["A" * 40]}
    tags = build_tags({}, twitch_cfg)
    assert tags == ["A" * 25]


def test_build_tags_case_insensitive_dedupe_preserves_first_seen_casing():
    twitch_cfg = {"base_tags": ["English", "english", "ENGLISH"]}
    tags = build_tags({}, twitch_cfg)
    assert tags == ["English"]


def test_build_tags_dedupe_across_base_and_game():
    twitch_cfg = {"base_tags": ["English"]}
    game_cfg = {"tags": ["english", "Rivals"]}
    tags = build_tags(game_cfg, twitch_cfg)
    assert tags == ["English", "Rivals"]


def test_build_tags_caps_list_at_10():
    twitch_cfg = {"base_tags": [f"Tag{i}" for i in range(15)]}
    tags = build_tags({}, twitch_cfg)
    assert len(tags) == 10
    assert tags == [f"Tag{i}" for i in range(10)]


def test_build_tags_empty_lists_ok():
    twitch_cfg = {"base_tags": []}
    game_cfg = {"tags": []}
    assert build_tags(game_cfg, twitch_cfg) == []
