"""Tests for dashboard_server.py's pure logic (no real socket/server started)."""

import json

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
