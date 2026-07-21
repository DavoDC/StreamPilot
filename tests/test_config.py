"""Tests for config.py"""

import json
import os
import sys
import pytest

# config.py uses a relative path from __file__, so we patch CONFIG_PATH
import config as cfg_module


def test_validate_passes_with_valid_config(tmp_path, monkeypatch):
    data = {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "Game Capture"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "sabnzbd": {"enabled": False, "host": "localhost", "port": 8080, "api_key": "key"},
        "poll_interval_seconds": 2,
        "games": {}
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    cfg = cfg_module.load()
    assert cfg["obs"]["host"] == "localhost"


def test_validate_fails_missing_obs_section(tmp_path, monkeypatch):
    data = {"twitch": {"client_id": "cid", "oauth_token": "tok"}, "games": {}}
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    with pytest.raises(SystemExit):
        cfg_module.load()


def test_validate_fails_missing_key(tmp_path, monkeypatch):
    data = {
        "obs": {"host": "localhost", "port": 4455, "game_capture_source": "Game Capture"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "games": {}
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    with pytest.raises(SystemExit):
        cfg_module.load()


def test_missing_config_file_exits(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(tmp_path / "nonexistent.json"))
    with pytest.raises(SystemExit):
        cfg_module.load()


def test_validate_fails_blacklisted_game_exe(tmp_path, monkeypatch):
    """Safety: never let a browser be configured as a 'game' - Twitch is public."""
    data = {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "Game Capture"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "games": {"chrome.exe": {"name": "Chrome", "twitch_game_id": "1", "obs_window": "Chrome:Chrome_WidgetWin_1:chrome.exe"}},
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    with pytest.raises(SystemExit):
        cfg_module.load()


def test_validate_fails_blacklisted_obs_window(tmp_path, monkeypatch):
    """Even if the exe key looks fine, a blacklisted obs_window must still fail."""
    data = {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "Game Capture"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "games": {"game.exe": {"name": "Game", "twitch_game_id": "1", "obs_window": "Explorer:CabinetWClass:explorer.exe"}},
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    with pytest.raises(SystemExit):
        cfg_module.load()


def test_load_handles_non_ascii_unicode_in_config(tmp_path, monkeypatch):
    """Regression: config.json written with literal unicode (e.g. per-game
    emoji, not \\uXXXX-escaped) must load on Windows regardless of the
    system's default codepage. Crashed 2026-07-21 when emoji were added to
    config.json - open() with no encoding fell back to cp1252 and raised
    UnicodeDecodeError on the multi-byte UTF-8 sequences. Silent under
    pythonw (stderr to devnull) - StreamPilot just vanished on hot-reload."""
    data = {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "Game Capture"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "games": {
            "game.exe": {"name": "Game", "twitch_game_id": "1", "obs_window": "Game:Class:game.exe", "emoji": "🐰"}
        },
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    cfg = cfg_module.load()
    assert cfg["games"]["game.exe"]["emoji"] == "🐰"


def test_add_game_writes_to_config(tmp_path, monkeypatch):
    data = {
        "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "GC"},
        "twitch": {"client_id": "cid", "oauth_token": "tok"},
        "games": {}
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(data))
    monkeypatch.setattr(cfg_module, "CONFIG_PATH", str(cfg_path))
    cfg_module.add_game("game.exe", "My Game", "12345", "My Game:MyClass:game.exe")
    result = json.loads(cfg_path.read_text())
    assert "game.exe" in result["games"]
    assert result["games"]["game.exe"]["name"] == "My Game"
    assert result["games"]["game.exe"]["twitch_game_id"] == "12345"
