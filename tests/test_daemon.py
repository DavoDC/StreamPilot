"""Tests for daemon.py"""

import pytest
from unittest.mock import MagicMock, patch, call
from daemon import Daemon

SAMPLE_CFG = {
    "obs": {"host": "localhost", "port": 4455, "password": "pw", "game_capture_source": "Game Capture"},
    "twitch": {"client_id": "cid", "oauth_token": "tok"},
    "sabnzbd": {"enabled": True, "host": "localhost", "port": 8080, "api_key": "key"},
    "poll_interval_seconds": 2,
    "games": {
        "game.exe": {
            "name": "My Game",
            "twitch_game_id": "12345",
            "obs_window": "My Game:GameClass:game.exe",
        }
    }
}


@pytest.fixture
def daemon():
    return Daemon(SAMPLE_CFG)


def test_detect_game_found(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "game.exe"
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        assert daemon._detect_game() == "game.exe"


def test_detect_game_not_found(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        assert daemon._detect_game() is None


def test_detect_game_empty_process_list(daemon):
    with patch("daemon.psutil.process_iter", return_value=[]):
        assert daemon._detect_game() is None


def test_on_game_launch_starts_stream_when_not_live(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.obs.set_game_capture_window.assert_called_once_with("My Game:GameClass:game.exe")
    daemon.twitch.set_game.assert_called_once_with("12345")
    daemon.obs.start_stream.assert_called_once()
    daemon.sab.pause.assert_called_once()


def test_on_game_launch_skips_start_when_already_live(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True

    daemon._on_game_launch("game.exe")

    daemon.obs.set_game_capture_window.assert_called_once()
    daemon.obs.start_stream.assert_not_called()
    daemon.sab.pause.assert_called_once()


def test_on_no_game_stops_stream(daemon):
    daemon.obs = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    daemon.obs.stop_stream.assert_called_once()
    daemon.sab.resume.assert_called_once()


def test_on_no_game_skips_if_no_active_game(daemon):
    daemon.obs = MagicMock()
    daemon._active_game_exe = None

    daemon._on_no_game()

    daemon.obs.stop_stream.assert_not_called()


def test_on_no_game_skips_stop_if_not_streaming(daemon):
    daemon.obs = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    daemon.obs.stop_stream.assert_not_called()
    daemon.sab.resume.assert_called_once()


def test_sab_disabled_does_not_call_sab(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab_enabled = False
    daemon.sab = MagicMock()
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.sab.pause.assert_not_called()
