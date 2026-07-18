"""Tests for dashboard_server.py's pure logic (no real socket/server started)."""

import http.client
import http.server
import json
import threading

import dashboard_server
import status_file


def test_status_json_bytes_returns_written_status(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(path, status="OK", game="Marvel Rivals", streaming=True, category="Marvel Rivals", sabnzbd="Paused", poll_interval=2)
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["status"] == "OK"
    assert data["game"] == "Marvel Rivals"


def test_status_json_bytes_missing_file_returns_offline_shape(tmp_path):
    data = json.loads(dashboard_server.status_json_bytes(tmp_path / "nope.json"))
    assert data["timestamp"] == 0
    assert data["status"] == "IDLE"


def test_status_json_bytes_includes_title_and_tags(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path, status="OK", game="Marvel Rivals", streaming=True, category="Marvel Rivals",
        sabnzbd="Paused", poll_interval=2, title="Davo plays Marvel Rivals!",
        tags=["English", "Australia", "MarvelRivals"],
    )
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["title"] == "Davo plays Marvel Rivals!"
    assert data["tags"] == ["English", "Australia", "MarvelRivals"]


def test_index_html_renders_title_and_tags_rows():
    """Dashboard rule: any daemon-controlled Twitch setting must be visible on
    the dashboard so David never needs to check Twitch/OBS directly."""
    html = dashboard_server.INDEX_HTML
    assert 'id="title"' in html
    assert 'id="tags"' in html
    assert "s.title" in html
    assert "s.tags" in html


def test_index_html_contains_expected_markers():
    html = dashboard_server.INDEX_HTML
    assert "<html" in html.lower()
    assert "/status.json" in html
    assert "StreamPilot" in html


def test_index_html_updates_tab_title_and_favicon():
    html = dashboard_server.INDEX_HTML
    assert "document.title" in html
    assert 'id="favicon"' in html
    assert "setFavicon" in html


def test_make_handler_only_serves_two_known_routes():
    # The handler class must not expose SimpleHTTPRequestHandler's directory
    # listing / arbitrary file serving - config.json must never be reachable.
    import http.server
    assert not issubclass(dashboard_server.Handler, http.server.SimpleHTTPRequestHandler)


def test_index_html_contains_quit_confirmation_dialog():
    html = dashboard_server.INDEX_HTML
    assert 'id="quitBtn"' in html
    assert 'id="quitDialog"' in html
    assert 'id="quitCancel"' in html
    assert 'id="quitConfirm"' in html
    assert "/quit" in html


def _run_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def test_post_quit_invokes_callback_and_returns_202():
    called = threading.Event()
    dashboard_server._on_quit_callback = called.set
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/quit")
        resp = conn.getresponse()
        assert resp.status == 202
        assert called.wait(timeout=1)
    finally:
        server.shutdown()
        dashboard_server._on_quit_callback = None


def test_post_quit_with_no_callback_registered_still_returns_202():
    dashboard_server._on_quit_callback = None
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/quit")
        resp = conn.getresponse()
        assert resp.status == 202
    finally:
        server.shutdown()


def test_post_unknown_route_returns_404():
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/nope")
        resp = conn.getresponse()
        assert resp.status == 404
    finally:
        server.shutdown()
