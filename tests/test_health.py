"""One health verdict shared by the tray, the badge and the favicon (WS-091): OK / ISSUE / IDLE / OFFLINE."""

import health


def test_fresh_status_keeps_its_own_state():
    s = {"timestamp": 100.0, "status": "OK", "poll_interval": 2}
    assert health.verdict(s, now=101.0) == "OK"
    assert health.verdict({**s, "status": "ISSUE"}, now=101.0) == "ISSUE"


def test_missing_or_unreachable_is_offline():
    assert health.verdict(None, now=1.0) == "OFFLINE"


def test_stale_is_offline_with_floor_of_eight_seconds():
    s = {"timestamp": 100.0, "status": "OK", "poll_interval": 1}
    assert health.verdict(s, now=107.0) == "OK"
    assert health.verdict(s, now=109.0) == "OFFLINE"


def test_stale_window_scales_with_poll_interval():
    s = {"timestamp": 100.0, "status": "IDLE", "poll_interval": 10}
    assert health.verdict(s, now=139.0) == "IDLE"
    assert health.verdict(s, now=141.0) == "OFFLINE"


def test_missing_status_field_is_idle():
    assert health.verdict({"timestamp": 100.0}, now=101.0) == "IDLE"


def test_colours_cover_every_state_and_match_the_dashboard_script():
    import dashboard_server
    for state, colour in health.COLOURS.items():
        assert f'{state}: "{colour}"' in dashboard_server.INDEX_HTML
    assert set(health.COLOURS) == {"OK", "ISSUE", "IDLE", "OFFLINE"}
