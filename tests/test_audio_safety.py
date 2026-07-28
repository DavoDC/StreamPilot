"""Tests for audio_safety.py - the allow-list guard that stops StreamPilot
from ever leaking Discord/Chrome/Signal audio to a public Twitch audience.

Pure-function tests only (no OBS calls) - the fixture below is copied from
the real probed source (scripts/probe_audio_source.py, 2026-07-28) and MUST
assert as fully safe. That is the single most important test in this file:
if it ever fails, the guard would refuse to stream on a correctly
configured OBS, which is a hard failure of the whole feature.
"""

import audio_safety


def _entry(exe, uuid="uuid-0"):
    return {"hidden": False, "selected": False, "uuid": uuid, "value": exe}


# --- Realistic fixture, copied from the live probed source (2026-07-28) ---

REAL_GAME_EXES = [
    "Marvel-Win64-Shipping.exe",
    "DeadByDaylight-Win64-Shipping.exe",
    "SSF2.exe",
    "FortniteClient-Win64-Shipping.exe",
    "DOOMEternalx64vk.exe",
    "javaw.exe",
    "OblivionRemastered-Win64-Shipping.exe",
    "SkyrimTogether.exe",
    "Overwatch.exe",
    "wwm.exe",
    "Palworld-Win64-Shipping.exe",
]

REALISTIC_SAFE_SETTINGS = {
    "executable_list": [_entry(exe, uuid=f"uuid-{i}") for i, exe in enumerate(REAL_GAME_EXES)],
    "active_session_list": "chrome.exe",
    # No 'mode' key, no 'exclude' key - both at OBS's safe defaults, omitted
    # by GetInputSettings. This is the trap the whole module is built around.
}

REALISTIC_ALLOWED = set(REAL_GAME_EXES)


def test_realistic_probed_settings_are_fully_safe():
    """THE most important test - a correctly configured live OBS must never
    be flagged as a violation."""
    violations = audio_safety.check_audio_settings(REALISTIC_SAFE_SETTINGS, REALISTIC_ALLOWED)
    assert violations == []


# --- extract_capture_exes ---

def test_extract_capture_exes_pulls_value_from_each_entry():
    settings = {"executable_list": [_entry("a.exe"), _entry("b.exe")]}
    assert audio_safety.extract_capture_exes(settings) == ["a.exe", "b.exe"]


def test_extract_capture_exes_missing_key_returns_empty():
    assert audio_safety.extract_capture_exes({}) == []


def test_extract_capture_exes_non_list_value_returns_empty():
    assert audio_safety.extract_capture_exes({"executable_list": "not a list"}) == []
    assert audio_safety.extract_capture_exes({"executable_list": None}) == []


def test_extract_capture_exes_tolerates_bare_string_entries():
    settings = {"executable_list": ["a.exe", "b.exe"]}
    assert audio_safety.extract_capture_exes(settings) == ["a.exe", "b.exe"]


def test_extract_capture_exes_tolerates_mixed_entries():
    settings = {"executable_list": ["a.exe", _entry("b.exe"), {"no_value": True}, 123, None]}
    assert audio_safety.extract_capture_exes(settings) == ["a.exe", "b.exe"]


def test_extract_capture_exes_not_a_dict_returns_empty():
    assert audio_safety.extract_capture_exes(None) == []
    assert audio_safety.extract_capture_exes("nope") == []


# --- resolve_mode / resolve_exclude ---

def test_resolve_mode_defaults_to_zero_when_absent():
    assert audio_safety.resolve_mode({}) == 0


def test_resolve_mode_returns_present_value():
    assert audio_safety.resolve_mode({"mode": 1}) == 1


def test_resolve_exclude_defaults_to_false_when_absent():
    assert audio_safety.resolve_exclude({}) is False


def test_resolve_exclude_returns_present_value():
    assert audio_safety.resolve_exclude({"exclude": True}) is True


def test_resolve_mode_malformed_settings_returns_default():
    assert audio_safety.resolve_mode(None) == 0


def test_resolve_exclude_malformed_settings_returns_default():
    assert audio_safety.resolve_exclude(None) is False


# --- resolve_exclude regression: fail closed on present-but-non-bool values ---
# A present-but-not-bool 'exclude' must resolve by truthiness, never fall
# back to the default - only an ABSENT key means default. This was a
# fail-open bug: a non-bool truthy value used to silently read as safe.

def test_resolve_exclude_absent_key_is_false():
    assert audio_safety.resolve_exclude({}) is False


def test_resolve_exclude_false_is_false():
    assert audio_safety.resolve_exclude({"exclude": False}) is False


def test_resolve_exclude_true_is_true():
    assert audio_safety.resolve_exclude({"exclude": True}) is True


def test_resolve_exclude_int_1_is_true():
    assert audio_safety.resolve_exclude({"exclude": 1}) is True


def test_resolve_exclude_string_true_is_true():
    assert audio_safety.resolve_exclude({"exclude": "true"}) is True


def test_resolve_exclude_int_0_is_false():
    assert audio_safety.resolve_exclude({"exclude": 0}) is False


def test_resolve_exclude_none_value_is_false():
    assert audio_safety.resolve_exclude({"exclude": None}) is False


def test_exclude_absent_key_settings_dict_is_safe():
    """The whole settings dict must still report SAFE when 'exclude' is
    absent entirely - this is the normal, correctly-configured case."""
    settings = {"executable_list": [_entry("game.exe")]}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert violations == []


def test_exclude_int_1_produces_exclude_inverted_stop():
    settings = {"executable_list": [_entry("game.exe")], "exclude": 1}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert any(v.severity == "stop" and v.code == "exclude_inverted" for v in violations)


def test_exclude_string_true_produces_exclude_inverted_stop():
    settings = {"executable_list": [_entry("game.exe")], "exclude": "true"}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert any(v.severity == "stop" and v.code == "exclude_inverted" for v in violations)


# --- check_audio_settings: severity ladder ---

def test_exclude_true_stops():
    settings = {"executable_list": [_entry("game.exe")], "exclude": True}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert any(v.severity == "stop" and v.code == "exclude_inverted" for v in violations)


def test_mode_1_stops():
    settings = {"executable_list": [_entry("game.exe")], "mode": 1}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert any(v.severity == "stop" and v.code == "wrong_mode" for v in violations)


def test_discord_present_stops():
    settings = {"executable_list": [_entry("game.exe"), _entry("discord.exe")]}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    denied = [v for v in violations if v.code == "denied_exe"]
    assert len(denied) == 1
    assert denied[0].severity == "stop"
    assert "discord.exe" in denied[0].message


def test_denied_exe_case_insensitive():
    settings = {"executable_list": [_entry("Discord.EXE")]}
    violations = audio_safety.check_audio_settings(settings, set())
    assert any(v.code == "denied_exe" for v in violations)


def test_unknown_exe_stops():
    settings = {"executable_list": [_entry("SomeRandomTool.exe")]}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    unknown = [v for v in violations if v.code == "unknown_exe"]
    assert len(unknown) == 1
    assert unknown[0].severity == "stop"
    assert "SomeRandomTool.exe" in unknown[0].message


def test_denied_exe_does_not_also_produce_unknown_exe():
    """A hard-denied exe gets exactly one violation, not two."""
    settings = {"executable_list": [_entry("discord.exe")]}
    violations = audio_safety.check_audio_settings(settings, set())
    codes = [v.code for v in violations]
    assert codes.count("denied_exe") == 1
    assert "unknown_exe" not in codes


def test_active_session_list_alone_does_not_stop():
    """active_session_list is only the properties-dialog dropdown selection,
    NOT captured audio - must never be flagged as a violation."""
    settings = {"executable_list": [_entry("game.exe")], "active_session_list": "chrome.exe"}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert violations == []


def test_empty_executable_list_warns():
    settings = {"executable_list": []}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert len(violations) == 1
    assert violations[0].severity == "warn"
    assert violations[0].code == "empty_list"


def test_missing_executable_list_key_warns():
    settings = {}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert any(v.code == "empty_list" for v in violations)


def test_allowed_game_exe_produces_no_violation():
    settings = {"executable_list": [_entry("game.exe")]}
    violations = audio_safety.check_audio_settings(settings, {"game.exe"})
    assert violations == []


def test_multiple_unknown_exes_produce_one_violation_each():
    settings = {"executable_list": [_entry("foo.exe"), _entry("bar.exe")]}
    violations = audio_safety.check_audio_settings(settings, set())
    unknown = [v for v in violations if v.code == "unknown_exe"]
    assert len(unknown) == 2


def test_malformed_settings_returns_unreadable_not_exception():
    for bad in (None, "not a dict", 123, ["list", "not", "dict"]):
        violations = audio_safety.check_audio_settings(bad, {"game.exe"})
        assert len(violations) == 1
        assert violations[0].severity == "stop"
        assert violations[0].code == "unreadable"


def test_check_audio_settings_never_raises_on_weird_input():
    weird_settings = {"executable_list": [{"value": None}, {"value": 12345}, {}]}
    # Should not raise
    audio_safety.check_audio_settings(weird_settings, {"game.exe"})


# --- check_missing_game ---

def test_check_missing_game_warns_when_absent():
    settings = {"executable_list": [_entry("other.exe")]}
    v = audio_safety.check_missing_game(settings, "game.exe")
    assert v is not None
    assert v.severity == "warn"
    assert v.code == "game_missing"
    assert "game.exe" in v.message


def test_check_missing_game_none_when_present():
    settings = {"executable_list": [_entry("game.exe")]}
    assert audio_safety.check_missing_game(settings, "game.exe") is None


def test_check_missing_game_case_insensitive():
    settings = {"executable_list": [_entry("Game.EXE")]}
    assert audio_safety.check_missing_game(settings, "game.exe") is None


def test_check_missing_game_none_when_no_game_running():
    settings = {"executable_list": [_entry("game.exe")]}
    assert audio_safety.check_missing_game(settings, None) is None


def test_check_missing_game_malformed_settings_does_not_raise():
    v = audio_safety.check_missing_game("not a dict", "game.exe")
    # Tolerant - malformed settings behave like an empty capture list here.
    assert v is None or v.code in ("game_missing", "unreadable")
