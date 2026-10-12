"""Tray (step 3): state from the one verdict, Quit dashboard stops ONLY the dashboard (D7). No real icon is created."""

import os

import pytest

import tray


def test_requested_only_for_live_port_and_not_when_opted_out():
    assert tray.requested(8765, env={}) is True
    assert tray.requested(8765, env={tray.NO_TRAY_ENV: "1"}) is False
    assert tray.requested(0, env={}) is False
    assert tray.requested(9000, env={}) is False


def test_status_text_names_game_and_state():
    s = {"timestamp": 10.0, "status": "OK", "poll_interval": 2, "game": "Fortnite"}
    assert tray.status_text(s, now=11.0) == "OK: Fortnite"
    assert tray.status_text({"timestamp": 10.0, "status": "IDLE", "poll_interval": 2}, now=11.0) == "Idle"
    assert tray.status_text(None, now=11.0) == tray.NOT_ANSWERING
    assert tray.status_text({"timestamp": 10.0, "status": "ISSUE", "poll_interval": 2, "game": "G"}, now=11.0).startswith("Issue")


def test_tooltip_carries_state():
    assert tray.tooltip(None, now=1.0).startswith("StreamPilot")
    assert "Dashboard not answering" in tray.tooltip(None, now=1.0)


def test_menu_labels_never_offer_to_stop_the_stream():
    labels = tray.menu_labels(None, now=1.0)
    assert labels[0] == "Open dashboard"
    assert tray.STOP_LABEL in labels
    assert not any("stream" in l.lower() and "stop" in l.lower() for l in labels)


def test_stop_dashboard_keeps_the_stream():
    calls = []
    tray.stop_dashboard(lambda **kw: calls.append(kw))
    assert calls == [{"end_stream": False}]


def test_request_reload_writes_trigger_without_force(tmp_path):
    p = str(tmp_path / "state" / "reload.trigger")
    tray.request_reload(p)
    assert os.path.exists(p)
    assert open(p).read().strip() != "force"  # a tray reload still waits for a live session


def test_fetch_status_unreachable_returns_none():
    assert tray.fetch_status(1, timeout=0.2) is None


def test_start_without_backend_logs_and_returns_false(monkeypatch):
    monkeypatch.setattr(tray, "_load_backend", lambda: None)
    logs = []
    assert tray.start(8765, on_stop=lambda **k: None, log=logs.append) is False
    assert "pystray" in logs[0]


def test_single_instance_guard_refuses_second(monkeypatch):
    monkeypatch.setattr(tray, "_load_backend", lambda: ("p", "I", "D"))
    monkeypatch.setattr(tray, "_acquire_mutex", lambda name: False)
    logs = []
    assert tray.start(8765, on_stop=lambda **k: None, log=logs.append) is False
    assert "already" in logs[0]


def test_icons_render_for_every_state():
    backend = tray._load_backend()
    if backend is None:
        pytest.skip("pystray/Pillow not installed")
    for name in tray.health.COLOURS:
        img = tray.render_icon(backend, name, 32)
        assert img.size == (32, 32)
