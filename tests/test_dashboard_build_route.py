"""/api/build route (WS-043) and exclusive bind with retry (WS-006)."""

import http.client
import json
import threading

import pytest

import dashboard_server


@pytest.fixture
def port():
    server = dashboard_server.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _get(port, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("GET", path, headers={"Host": host or f"localhost:{port}"})
    r = conn.getresponse()
    return r, r.read()


def test_api_build_returns_identity(port):
    r, body = _get(port, "/api/build")
    data = json.loads(body)
    assert r.status == 200
    for key in ("app", "line", "sha", "dirty", "date", "boot_id", "started_at", "pid"):
        assert key in data
    assert data["app"] == "StreamPilot"


def test_api_build_obeys_host_guard(port):
    r, _ = _get(port, "/api/build", host="evil.example")
    assert r.status == 403


def test_second_bind_on_same_port_fails_fast(port):
    with pytest.raises(OSError):
        dashboard_server.bind_with_retry(port, attempts=2, delay=0)


def test_bind_with_retry_succeeds_after_port_frees(monkeypatch):
    calls = {"n": 0}
    real = dashboard_server.make_server

    def flaky(p, host=dashboard_server.BIND_HOST):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("in use")
        return real(0)

    monkeypatch.setattr(dashboard_server, "make_server", flaky)
    server = dashboard_server.bind_with_retry(1234, attempts=5, delay=0)
    server.server_close()
    assert calls["n"] == 3
