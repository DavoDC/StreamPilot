"""Dashboard test harness (WS-093 and neighbours): data-testid, ARIA, [app-error], build footer, /status.json contract, fixture mode, /__log."""

import http.client
import json
import re
import threading

import pytest

import dashboard_server


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(dashboard_server, "_fixture", None)
    monkeypatch.setattr(dashboard_server, "_log_count", 0)


@pytest.fixture
def port():
    server = dashboard_server.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _req(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    h = {"Host": f"localhost:{port}"}
    h.update(headers or {})
    conn.request(method, path, body=body, headers=h)
    r = conn.getresponse()
    return r.status, r.read()


def _post_headers(port):
    return {"Origin": f"http://localhost:{port}", dashboard_server.TOKEN_HEADER: dashboard_server.TOKEN,
            "Content-Type": "application/json"}


def _html():
    return dashboard_server.index_html_bytes().decode("utf-8")


# --- markup ---

REQUIRED_TESTIDS = ["badge", "dot", "video", "audio", "category", "uptime", "title", "tags", "sabnzbd", "sab-activity",
                    "sab-toggle", "restart-btn", "quit-btn", "footer", "build", "error-banner", "card-obs", "card-twitch",
                    "card-sab", "quit-cancel", "quit-keep-stream", "quit-end-stream", "restart-cancel", "restart-confirm"]


@pytest.mark.parametrize("tid", REQUIRED_TESTIDS)
def test_every_element_has_a_testid(tid):
    assert f'data-testid="{tid}"' in _html()


def test_every_button_has_a_testid():
    for tag in re.findall(r"<button\s[^>]*>", _html()):
        assert "data-testid=" in tag, tag


def test_aria_on_status_banner_and_decoration():
    html = _html()
    assert re.search(r'id="badge"[^>]*role="status"', html)
    assert re.search(r'id="dot"[^>]*aria-hidden="true"', html)
    assert re.search(r'id="error-banner"[^>]*role="alert"[^>]*hidden', html)
    assert re.search(r'id="sabToggle"[^>]*aria-label="[^"]+"', html)
    for card in ("OBS", "Twitch", "SABnzbd"):
        assert f'aria-label="{card}"' in html


def test_error_banner_handler_logs_app_error_and_shows_text():
    html = _html()
    assert "window.addEventListener(\"error\"" in html
    assert "unhandledrejection" in html
    assert "[app-error]" in html


def test_debug_handle_exposes_state_and_help():
    html = _html()
    assert "window.__debug" in html
    assert "state()" in html and "help()" in html


def test_footer_build_line_is_server_rendered():
    html = _html()
    m = re.search(r'data-testid="build"[^>]*>\s*(StreamPilot [0-9a-f]+|StreamPilot unknown) [^<]*<', html)
    assert m, "build line missing"


# --- /status.json contract ---

def test_status_json_adds_schema_and_stale_fields(port, monkeypatch):
    monkeypatch.setattr(dashboard_server.status_file, "read_status", lambda path: None)  # never read the live file
    code, body = _req(port, "GET", "/status.json")
    data = json.loads(body)
    assert code == 200
    assert data["schema"] == dashboard_server.STATUS_SCHEMA
    assert isinstance(data["generated_at"], float)
    assert data["stale"] is True  # nothing fresh in the real state file under test, or a dead daemon
    assert "poll_interval" in data


# --- fixture mode ---

def test_fixture_mode_serves_the_scenario_not_live_data(port):
    dashboard_server.set_fixture("live")
    data = json.loads(_req(port, "GET", "/status.json")[1])
    assert data["status"] == "OK" and data["game"] == "Palworld"
    assert data["stale"] is False


def test_fixture_stale_scenario_reports_stale(port):
    dashboard_server.set_fixture("stale")
    assert json.loads(_req(port, "GET", "/status.json")[1])["stale"] is True


def test_fixture_banner_is_visible_only_in_fixture_mode():
    assert 'data-testid="fixture-banner"' not in _html()
    dashboard_server.set_fixture("issue")
    html = _html()
    assert re.search(r'data-testid="fixture-banner"[^>]*>[^<]*FIXTURE[^<]*issue', html)


def test_fixture_mode_posts_never_reach_the_daemon(port):
    called = []
    dashboard_server._on_quit_callback = lambda **kw: called.append(kw)
    try:
        dashboard_server.set_fixture("live")
        code, _ = _req(port, "POST", "/quit", body=b'{"end_stream": true}', headers=_post_headers(port))
        assert code == 202
        assert called == []
    finally:
        dashboard_server._on_quit_callback = None


def test_unknown_fixture_name_is_rejected():
    with pytest.raises(ValueError):
        dashboard_server.set_fixture("nope")


# --- /__log ---

def test_log_route_writes_a_line_with_the_guard(port, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_server, "UI_LOG_PATH", str(tmp_path / "ui.log"))
    code, _ = _req(port, "POST", "/__log", body=json.dumps({"msg": "[app-error] boom"}).encode(), headers=_post_headers(port))
    assert code == 204
    assert "[app-error] boom" in (tmp_path / "ui.log").read_text(encoding="utf-8")


def test_log_route_refuses_without_token(port, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_server, "UI_LOG_PATH", str(tmp_path / "ui.log"))
    h = _post_headers(port)
    h.pop(dashboard_server.TOKEN_HEADER)
    code, _ = _req(port, "POST", "/__log", body=b'{"msg":"x"}', headers=h)
    assert code == 403
    assert not (tmp_path / "ui.log").exists()


def test_log_route_is_capped_and_truncates(port, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_server, "UI_LOG_PATH", str(tmp_path / "ui.log"))
    monkeypatch.setattr(dashboard_server, "LOG_MAX_LINES", 2)
    for _ in range(4):
        _req(port, "POST", "/__log", body=json.dumps({"msg": "x" * 5000}).encode(), headers=_post_headers(port))
    lines = (tmp_path / "ui.log").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(len(l) < 1200 for l in lines)


def test_a_query_string_does_not_change_the_route(port):
    assert _req(port, "GET", "/?scenario=live")[0] == 200
    assert _req(port, "GET", "/status.json?x=1")[0] == 200
    assert _req(port, "GET", "/nope?x=1")[0] == 404


def test_body_grows_with_content_instead_of_clipping_the_top():
    # height:100vh plus justify-content:center pushes tall content above the viewport where it cannot be scrolled to.
    assert "min-height: 100vh" in _html()
    assert not re.search(r"body \{[^}]*[^-]height: 100vh", _html())
