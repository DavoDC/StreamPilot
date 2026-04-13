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
