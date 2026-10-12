"""ui_check and capture (WS-093): the page must paint exactly what /status.json says, and every scenario must render cleanly."""

import re

import capture
import fixtures
import health
import ui_check


def fake_dom(status, now, banner_hidden=True, build=True, testids=True):
    """A minimal dump-dom in the shape the real page produces after one tick, built from a status dict."""
    state = health.verdict(status, now)
    stale = state == "OFFLINE"
    game = status.get("game")
    audio = "-"
    if not stale and game and status.get("audio_ok") is not None:
        audio = ", ".join(status["audio_exes"]) if status["audio_ok"] else "; ".join(status["audio_violations"])
    tags = "".join(f'<span class="tag">{t}</span>' for t in ([] if stale else (status.get("tags") or [])))
    video = "-" if stale or not game else status["captured_window_exe"]
    return (
        '<div id="error-banner" data-testid="error-banner" role="alert"' + (" hidden" if banner_hidden else "") + "></div>"
        '<div id="fixture-banner" data-testid="fixture-banner">FIXTURE: x (not live data)</div>'
        f'<div id="badge" data-testid="badge" role="status">{state}</div>'
        f'<span class="value" id="video" data-testid="video">{video}</span>'
        f'<span class="value" id="audio" data-testid="audio">{audio}</span>'
        f'<span class="value" id="category" data-testid="category">{"-" if stale else (status.get("category") or "Unknown")}</span>'
        f'<span class="value" id="title" data-testid="title">{"-" if stale else (status.get("title") or "-")}</span>'
        f'<span class="value" id="tags" data-testid="tags">{tags}</span>'
        + ('<div id="build" data-testid="build">StreamPilot abc1234 2026-10-12</div>' if build else "")
        + ("<button data-testid=\"quit-btn\">Quit</button>" if testids else "<button>Quit</button>")
    )


def test_ui_check_passes_when_the_page_matches_every_scenario():
    for name in fixtures.SCENARIOS:
        status = fixtures.status(name, now=1000.0)
        assert ui_check.check_dom(status, fake_dom(status, 1000.0), now=1000.0) == [], name


def test_ui_check_catches_a_wrong_badge():
    status = fixtures.status("live", now=1000.0)
    dom = fake_dom(status, 1000.0).replace(">OK</div>", ">IDLE</div>")
    assert any("badge" in p for p in ui_check.check_dom(status, dom, now=1000.0))


def test_ui_check_catches_missing_audio_violation_text():
    status = fixtures.status("issue", now=1000.0)
    dom = fake_dom(status, 1000.0).replace(status["audio_violations"][0], "all fine")
    assert any("audio" in p for p in ui_check.check_dom(status, dom, now=1000.0))


def test_ui_check_catches_wrong_tag_count():
    status = fixtures.status("live", now=1000.0)
    dom = fake_dom(status, 1000.0).replace('<span class="tag">English</span>', "")
    assert any("tags" in p for p in ui_check.check_dom(status, dom, now=1000.0))


def test_verify_dom_clean_page_passes():
    status = fixtures.status("live", now=1000.0)
    assert capture.verify_dom(fake_dom(status, 1000.0), "") == []


def test_verify_dom_flags_app_error_visible_banner_missing_build_and_testids():
    status = fixtures.status("live", now=1000.0)
    assert any("app-error" in p for p in capture.verify_dom(fake_dom(status, 1000.0), "CONSOLE [app-error] boom"))
    assert any("banner" in p for p in capture.verify_dom(fake_dom(status, 1000.0, banner_hidden=False), ""))
    assert any("build" in p for p in capture.verify_dom(fake_dom(status, 1000.0, build=False), ""))
    assert any("testid" in p for p in capture.verify_dom(fake_dom(status, 1000.0, testids=False), ""))


def test_verify_dom_flags_a_page_that_never_loaded():
    assert capture.verify_dom("", "")


def test_capture_runs_every_scenario_with_an_injected_visitor(tmp_path):
    seen = []

    def visit(chrome, url, png):
        seen.append(url)
        png.write_bytes(b"png")
        name = re.search(r"scenario=([a-z-]+)", url)
        return "", ""

    results = capture.capture(tmp_path, "chrome.exe", visit=visit, serve=lambda name: ("http://localhost:1", lambda: None))
    assert set(results) == set(fixtures.SCENARIOS)
    assert len(seen) == len(fixtures.SCENARIOS)
    assert all((tmp_path / f"{n}.png").exists() for n in fixtures.SCENARIOS)
    assert all(results[n] for n in results)  # an empty dom fails every scenario


def test_find_chrome_returns_a_path_or_none():
    found = capture.find_chrome()
    assert found is None or found.lower().endswith((".exe",))


def test_cli_lists_scenarios_and_fails_cleanly_without_chrome(monkeypatch, capsys):
    monkeypatch.setattr(capture, "find_chrome", lambda: None)
    assert capture.main(["--fixture"]) == 2
    assert "Chrome" in capsys.readouterr().out
