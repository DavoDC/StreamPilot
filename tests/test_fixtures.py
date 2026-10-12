"""Fixture scenarios (WS-093): the same status contract the daemon writes, for the harness, never live data."""

import health
import fixtures

KEYS = {"timestamp", "status", "game", "streaming", "category", "sabnzbd", "poll_interval", "title", "tags",
        "build_id", "audio_ok", "audio_violations", "captured_window_exe", "audio_exes", "blacklisted_window",
        "stream_started_at", "sab_auto_manage"}


def test_every_scenario_has_the_full_contract():
    assert set(fixtures.SCENARIOS) == {"idle", "live", "issue", "offline", "stale", "long-title"}
    for name in fixtures.SCENARIOS:
        s = fixtures.status(name, now=1000.0)
        assert KEYS <= set(s), (name, KEYS - set(s))


def test_scenarios_produce_the_state_they_are_named_for():
    assert health.verdict(fixtures.status("idle", now=1000.0), now=1000.0) == "IDLE"
    assert health.verdict(fixtures.status("live", now=1000.0), now=1000.0) == "OK"
    assert health.verdict(fixtures.status("issue", now=1000.0), now=1000.0) == "ISSUE"
    assert health.verdict(fixtures.status("stale", now=1000.0), now=1000.0) == "OFFLINE"
    assert health.verdict(fixtures.status("offline", now=1000.0), now=1000.0) == "OFFLINE"


def test_issue_violation_text_comes_from_the_real_audio_guard():
    s = fixtures.status("issue", now=1000.0)
    assert s["audio_ok"] is False and s["audio_violations"]


def test_long_title_is_long_enough_to_stress_the_layout():
    s = fixtures.status("long-title", now=1000.0)
    assert len(s["title"]) > 120 and len(s["tags"]) >= 10


def test_unknown_scenario_is_a_clear_error():
    import pytest
    with pytest.raises(ValueError) as e:
        fixtures.status("nope")
    assert "idle" in str(e.value)
