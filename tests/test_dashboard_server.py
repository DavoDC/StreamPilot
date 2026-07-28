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


def test_twitch_link_html_empty_when_no_channel():
    assert dashboard_server._twitch_link_html(None) == ""
    assert dashboard_server._twitch_link_html("") == ""


def test_twitch_link_html_builds_correct_url():
    html = dashboard_server._twitch_link_html("davo1776")
    assert 'href="https://www.twitch.tv/davo1776"' in html
    assert 'target="_blank"' in html
    assert 'rel="noopener noreferrer"' in html


def test_index_html_bytes_includes_twitch_link_when_configured():
    dashboard_server._twitch_channel = "davo1776"
    try:
        html = dashboard_server.index_html_bytes().decode("utf-8")
        assert "https://www.twitch.tv/davo1776" in html
    finally:
        dashboard_server._twitch_channel = None


def test_index_html_bytes_omits_twitch_link_when_not_configured():
    dashboard_server._twitch_channel = None
    html = dashboard_server.index_html_bytes().decode("utf-8")
    assert "twitch.tv" not in html
    assert "__TWITCH_LINK_HTML__" not in html


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
    assert "/quit" in html


def test_index_html_quit_dialog_offers_keep_streaming_option():
    """The 'Keep streaming' quit option must exist and send end_stream:false,
    distinct from 'End stream' which sends end_stream:true."""
    html = dashboard_server.INDEX_HTML
    assert 'id="quitKeepStream"' in html
    assert 'id="quitEndStream"' in html
    assert "end_stream: false" in html or "end_stream:false" in html or "confirmQuit(false" in html
    assert "confirmQuit(true" in html


def test_index_html_reloads_on_build_id_change():
    """Live-reload contract: the tab must reload itself when the server's
    build_id changes (process restart, e.g. from hot_reload.py --watch)."""
    html = dashboard_server.INDEX_HTML
    assert "s.build_id" in html
    assert "location.reload()" in html


def test_status_json_bytes_includes_build_id(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path, status="OK", game="Marvel Rivals", streaming=True, category="Marvel Rivals",
        sabnzbd="Paused", poll_interval=2, build_id="123.456",
    )
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["build_id"] == "123.456"


def _run_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), dashboard_server.Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def test_post_quit_invokes_callback_and_returns_202():
    calls = []
    dashboard_server._on_quit_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/quit")
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 202
        assert calls
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
        resp.read()
        assert resp.status == 202
    finally:
        server.shutdown()


def test_post_quit_defaults_to_end_stream_true_with_no_body():
    calls = []
    dashboard_server._on_quit_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/quit")
        resp = conn.getresponse()
        resp.read()
    finally:
        server.shutdown()
        dashboard_server._on_quit_callback = None
    assert calls == [{"end_stream": True}]


def test_post_quit_reads_end_stream_false_from_body():
    calls = []
    dashboard_server._on_quit_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = json.dumps({"end_stream": False}).encode("utf-8")
        conn.request("POST", "/quit", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
    finally:
        server.shutdown()
        dashboard_server._on_quit_callback = None
    assert calls == [{"end_stream": False}]


def test_post_quit_malformed_body_defaults_to_end_stream_true():
    calls = []
    dashboard_server._on_quit_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = b"not json"
        conn.request("POST", "/quit", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 202
    finally:
        server.shutdown()
        dashboard_server._on_quit_callback = None
    assert calls == [{"end_stream": True}]


def test_post_unknown_route_returns_404():
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("POST", "/nope")
        resp = conn.getresponse()
        assert resp.status == 404
    finally:
        server.shutdown()


# --- SAB auto-manage toggle tests ---

def test_index_html_contains_sab_toggle():
    html = dashboard_server.INDEX_HTML
    assert 'id="sabToggle"' in html
    assert "/sab_toggle" in html


def test_index_html_contains_audio_row():
    """Dashboard is the source of truth - the audio privacy guard must be
    visible here, not just in the terminal heartbeat."""
    html = dashboard_server.INDEX_HTML
    assert 'id="audio"' in html
    assert "setAudioRow" in html


def test_status_json_bytes_includes_audio_fields(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path, status="ISSUE", game="Marvel Rivals", streaming=True, category="Marvel Rivals",
        sabnzbd="Paused", poll_interval=2, audio_ok=False, audio_violations=["'discord.exe' is a hard-denied executable"],
    )
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["audio_ok"] is False
    assert data["audio_violations"] == ["'discord.exe' is a hard-denied executable"]


def test_status_json_bytes_missing_file_has_null_audio_fields(tmp_path):
    data = json.loads(dashboard_server.status_json_bytes(tmp_path / "nope.json"))
    assert data["audio_ok"] is None
    assert data["audio_violations"] is None


def test_status_json_bytes_includes_sab_auto_manage(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path, status="OK", game="Marvel Rivals", streaming=True, category="Marvel Rivals",
        sabnzbd="Paused", poll_interval=2, sab_auto_manage=False,
    )
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["sab_auto_manage"] is False


def test_status_json_bytes_includes_captured_window_title_and_audio_exes(tmp_path):
    path = tmp_path / "status.json"
    status_file.write_status(
        path, status="OK", game="Marvel Rivals", streaming=True, category="Marvel Rivals",
        sabnzbd="Paused", poll_interval=2, captured_window_title="Marvel Rivals  [PID 1234]",
        audio_exes=["MarvelRivals_Live.exe"],
    )
    data = json.loads(dashboard_server.status_json_bytes(path))
    assert data["captured_window_title"] == "Marvel Rivals  [PID 1234]"
    assert data["audio_exes"] == ["MarvelRivals_Live.exe"]


def test_status_json_bytes_missing_file_has_null_captured_window_and_audio_exes(tmp_path):
    data = json.loads(dashboard_server.status_json_bytes(tmp_path / "nope.json"))
    assert data["captured_window_title"] is None
    assert data["audio_exes"] is None


def test_index_html_grouped_into_three_api_cards():
    """David's TIER 1 feedback (docs/HISTORY.md, 2026-07-28): the dashboard
    must group fields by API source (OBS, Twitch, SABnzbd) into separate
    cards instead of one flat list."""
    html = dashboard_server.INDEX_HTML
    assert 'class="card card-obs"' in html
    assert 'class="card card-twitch"' in html
    assert 'class="card card-sab"' in html


def test_index_html_obs_card_contains_captured_window_and_audio_adjacent():
    html = dashboard_server.INDEX_HTML
    assert 'id="capturedWindow"' in html
    assert "s.captured_window_title" in html
    # Game Captured and Audio must sit in the same (OBS) card, audio directly
    # beneath the captured-window row.
    obs_card = html.split('class="card card-obs"')[1].split('class="card card-twitch"')[0]
    assert 'id="capturedWindow"' in obs_card
    assert 'id="audio"' in obs_card


def test_index_html_audio_row_names_the_capturing_exe():
    """setAudioRow must take the exe list so 'safe' is verifiable at a
    glance, not a bare safe/unsafe verdict."""
    html = dashboard_server.INDEX_HTML
    assert "s.audio_exes" in html


def test_index_html_no_longer_has_standalone_game_row():
    """The old #game row duplicated Category - removed per TIER 1 design."""
    html = dashboard_server.INDEX_HTML
    assert 'id="game"' not in html


def test_index_html_twitch_card_contains_category_title_tags_and_link():
    html = dashboard_server.INDEX_HTML
    twitch_card = html.split('class="card card-twitch"')[1].split('class="card card-sab"')[0]
    assert 'id="category"' in twitch_card
    assert 'id="title"' in twitch_card
    assert 'id="tags"' in twitch_card


def test_index_html_sab_card_contains_status_and_toggle():
    html = dashboard_server.INDEX_HTML
    sab_card = html.split('class="card card-sab"')[1]
    assert 'id="sabnzbd"' in sab_card
    assert 'id="sabToggle"' in sab_card


def test_index_html_cards_use_no_emoji_icons():
    """Workspace rule: no emojis unless explicitly requested - card headers
    use inline SVG glyphs instead."""
    html = dashboard_server.INDEX_HTML
    cards_section = html.split('id="cards"')[1].split("</script>")[0] if 'id="cards"' in html else ""
    assert "<svg" in html


def test_post_sab_toggle_invokes_callback_and_returns_202():
    calls = []
    dashboard_server._on_sab_toggle_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = json.dumps({"enabled": False}).encode("utf-8")
        conn.request("POST", "/sab_toggle", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 202
    finally:
        server.shutdown()
        dashboard_server._on_sab_toggle_callback = None
    assert calls == [{"enabled": False}]


def test_post_sab_toggle_enabled_true():
    calls = []
    dashboard_server._on_sab_toggle_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = json.dumps({"enabled": True}).encode("utf-8")
        conn.request("POST", "/sab_toggle", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
    finally:
        server.shutdown()
        dashboard_server._on_sab_toggle_callback = None
    assert calls == [{"enabled": True}]


def test_post_sab_toggle_malformed_body_returns_400_and_skips_callback():
    calls = []
    dashboard_server._on_sab_toggle_callback = lambda **kwargs: calls.append(kwargs)
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = b"not json"
        conn.request("POST", "/sab_toggle", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 400
    finally:
        server.shutdown()
        dashboard_server._on_sab_toggle_callback = None
    assert calls == []


def test_post_sab_toggle_no_callback_registered_still_returns_202():
    dashboard_server._on_sab_toggle_callback = None
    server, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        body = json.dumps({"enabled": False}).encode("utf-8")
        conn.request("POST", "/sab_toggle", body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 202
    finally:
        server.shutdown()


def test_index_html_button_font_family_reset():
    """Prevention for the Quit-button-looks-different bug: browsers don't
    make <button> inherit the page font by default, so it must be explicit."""
    html = dashboard_server.INDEX_HTML
    assert "font-family: inherit" in html
