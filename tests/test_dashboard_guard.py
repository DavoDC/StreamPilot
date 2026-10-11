"""Security guard tests (WS-020 to WS-022, WS-032): Host allowlist, same-origin
check, per-launch token on every POST, loopback bind, response headers."""

import http.client
import http.server
import json
import re
import threading

import pytest

import dashboard_server

POST_ROUTES = [
    ("/quit", b'{"end_stream": false}'),
    ("/sab_toggle", b'{"enabled": true}'),
    ("/restart_stream", b""),
]


@pytest.fixture
def served():
    calls = []
    dashboard_server._on_quit_callback = lambda **kw: calls.append("quit")
    dashboard_server._on_sab_toggle_callback = lambda **kw: calls.append("sab")
    dashboard_server._on_restart_stream_callback = lambda: calls.append("restart")
    server = dashboard_server.make_server(0)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield port, calls
    server.shutdown()
    server.server_close()
    dashboard_server._on_quit_callback = None
    dashboard_server._on_sab_toggle_callback = None
    dashboard_server._on_restart_stream_callback = None


def _req(port, method, path, body=b"", headers=None, host="default"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    h = {} if headers is None else dict(headers)
    if host != "default":
        h["Host"] = host
    conn.request(method, path, body=body or None, headers=h)
    resp = conn.getresponse()
    data = resp.read()
    return resp, data


def _good(port, token=True):
    h = {"Origin": f"http://localhost:{port}", "Content-Type": "application/json"}
    if token:
        h["X-StreamPilot-Token"] = dashboard_server.TOKEN
    return h


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_valid_guard_is_accepted(served, path, body):
    port, calls = served
    resp, _ = _req(port, "POST", path, body, _good(port))
    assert resp.status == 202
    assert len(calls) == 1


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_without_token_is_403(served, path, body):
    port, calls = served
    resp, _ = _req(port, "POST", path, body, _good(port, token=False))
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_wrong_token_is_403(served, path, body):
    port, calls = served
    h = _good(port)
    h["X-StreamPilot-Token"] = "nope"
    resp, _ = _req(port, "POST", path, body, h)
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_foreign_origin_is_403(served, path, body):
    port, calls = served
    h = _good(port)
    h["Origin"] = "http://evil.example"
    resp, _ = _req(port, "POST", path, body, h)
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_wrong_port_origin_is_403(served, path, body):
    port, calls = served
    h = _good(port)
    h["Origin"] = f"http://localhost:{port + 1}"
    resp, _ = _req(port, "POST", path, body, h)
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_no_origin_or_referer_is_403(served, path, body):
    port, calls = served
    h = _good(port)
    del h["Origin"]
    resp, _ = _req(port, "POST", path, body, h)
    assert resp.status == 403
    assert calls == []


def test_post_with_same_origin_referer_only_is_accepted(served):
    port, calls = served
    h = _good(port)
    del h["Origin"]
    h["Referer"] = f"http://127.0.0.1:{port}/"
    resp, _ = _req(port, "POST", "/restart_stream", b"", h)
    assert resp.status == 202


def test_post_with_null_origin_is_403(served):
    port, calls = served
    h = _good(port)
    h["Origin"] = "null"
    resp, _ = _req(port, "POST", "/quit", b"{}", h)
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path,body", POST_ROUTES)
def test_post_with_foreign_host_is_403(served, path, body):
    port, calls = served
    resp, _ = _req(port, "POST", path, body, _good(port), host="evil.example")
    assert resp.status == 403
    assert calls == []


@pytest.mark.parametrize("path", ["/", "/status.json"])
def test_get_with_foreign_host_is_403(served, path):
    port, _ = served
    resp, data = _req(port, "GET", path, host=f"rebind.example:{port}")
    assert resp.status == 403
    assert b"token" not in data.lower()


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_get_host_variants_without_port_or_with_port(served, host):
    port, _ = served
    for h in (f"{host}:{port}",):
        resp, _ = _req(port, "GET", "/status.json", host=h)
        if host == "[::1]":
            assert resp.status == 403  # server binds IPv4 only; not allowlisted
        else:
            assert resp.status == 200


def test_get_wrong_port_host_is_403(served):
    port, _ = served
    resp, _ = _req(port, "GET", "/status.json", host=f"localhost:{port + 1}")
    assert resp.status == 403


def test_page_embeds_the_token_and_js_sends_it():
    html = dashboard_server.index_html_bytes().decode()
    assert dashboard_server.TOKEN in html
    assert "__STREAMPILOT_TOKEN__" not in html
    assert html.count("X-StreamPilot-Token") >= 1
    # every state-changing fetch goes through the helper that adds the token
    assert len(re.findall(r'fetch\("/(?:quit|sab_toggle|restart_stream)"', html)) == 0
    assert len(re.findall(r'postAction\("/(?:quit|sab_toggle|restart_stream)"', html)) == 3


def test_token_is_long_and_random_per_process():
    assert len(dashboard_server.TOKEN) >= 24


def test_served_page_contains_token_end_to_end(served):
    port, _ = served
    resp, data = _req(port, "GET", "/")
    assert resp.status == 200
    assert dashboard_server.TOKEN in data.decode()


def test_security_headers_on_page_and_json(served):
    port, _ = served
    for path in ("/", "/status.json"):
        resp, _ = _req(port, "GET", path)
        assert resp.getheader("Cache-Control") == "no-store"
        assert resp.getheader("X-Content-Type-Options") == "nosniff"
        csp = resp.getheader("Content-Security-Policy")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


def test_no_cors_headers_ever(served):
    port, _ = served
    resp, _ = _req(port, "GET", "/status.json", headers={"Origin": "http://evil.example"})
    assert resp.getheader("Access-Control-Allow-Origin") is None
    resp, _ = _req(port, "OPTIONS", "/quit", headers={"Origin": "http://evil.example"})
    assert resp.getheader("Access-Control-Allow-Origin") is None


def test_rejection_body_has_no_secret(served):
    port, _ = served
    resp, data = _req(port, "POST", "/quit", b"{}", {"Origin": "http://evil.example"})
    assert resp.status == 403
    assert dashboard_server.TOKEN not in data.decode()


def test_bind_host_is_loopback_constant():
    assert dashboard_server.BIND_HOST == "127.0.0.1"
    server = dashboard_server.make_server(0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_non_loopback_bind_is_refused():
    with pytest.raises(ValueError):
        dashboard_server.make_server(0, host="0.0.0.0")
