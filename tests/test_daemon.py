"""Tests for daemon.py"""

import copy
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
    return Daemon(copy.deepcopy(SAMPLE_CFG))


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


def test_on_game_launch_stops_then_starts_stream_on_switch(daemon):
    """Game-per-VOD: if a stream is live when a game launches, end it and start a fresh one."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True

    daemon._on_game_launch("game.exe")

    daemon.obs.stop_stream.assert_called_once()
    daemon.obs.start_stream.assert_called_once()
    stop_idx = daemon.obs.method_calls.index(call.stop_stream())
    start_idx = daemon.obs.method_calls.index(call.start_stream())
    assert stop_idx < start_idx, "stop_stream must be called before start_stream"
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


def test_ensure_obs_running_already_running(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "obs64.exe"
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        result = daemon._ensure_obs_running()
    assert result is False


def test_ensure_obs_running_no_exe_path(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        result = daemon._ensure_obs_running()
    assert result is False


def test_ensure_obs_running_launches_obs(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    daemon.cfg["obs"]["exe_path"] = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
    daemon.obs = MagicMock()
    daemon.obs.connect.return_value = True

    with patch("daemon.psutil.process_iter", return_value=[mock_proc]), \
         patch("daemon.subprocess.Popen") as mock_popen, \
         patch("daemon.time.sleep"):
        result = daemon._ensure_obs_running()

    mock_popen.assert_called_once_with(
        [r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"],
        cwd=r"C:\Program Files\obs-studio\bin\64bit",
    )
    assert result is True


def test_ensure_obs_running_obs_timeout(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "chrome.exe"
    daemon.cfg["obs"]["exe_path"] = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
    daemon.obs = MagicMock()
    daemon.obs.connect.return_value = False

    with patch("daemon.psutil.process_iter", return_value=[mock_proc]), \
         patch("daemon.subprocess.Popen"), \
         patch("daemon.time.sleep"):
        result = daemon._ensure_obs_running()

    assert result is False


def test_sab_disabled_does_not_call_sab(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab_enabled = False
    daemon.sab = MagicMock()
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.sab.pause.assert_not_called()


# --- Heartbeat tests ---
# _format_heartbeat no longer takes a timestamp param - logging framework adds it uniformly.

def test_format_heartbeat_game_active_all_good(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=True,
    )
    assert "My Game" in line
    assert "SABnzbd: Paused" in line
    assert "should be" not in line
    assert "Status: OK" in line


def test_format_heartbeat_no_embedded_timestamp(daemon):
    line = daemon._format_heartbeat(
        game_name=None, obs_streaming=False, twitch_category=None, sab_paused=None
    )
    # Logging adds the timestamp; the message itself must not start with one
    assert not line.startswith("[")


def test_format_heartbeat_status_issue_when_obs_offline(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=False,
        twitch_category="My Game",
        sab_paused=True,
    )
    assert "Status: ISSUE" in line


def test_format_heartbeat_status_issue_when_sab_running(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
    )
    assert "Status: ISSUE" in line


def test_format_heartbeat_status_issue_when_sab_unreachable_gaming(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=None,
    )
    assert "Status: ISSUE" in line


def test_format_heartbeat_status_ok_when_idle(daemon):
    line = daemon._format_heartbeat(
        game_name=None,
        obs_streaming=False,
        twitch_category=None,
        sab_paused=None,
    )
    assert "Status: OK" in line


def test_format_heartbeat_obs_offline_while_game_active(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=False,
        twitch_category="My Game",
        sab_paused=True,
    )
    assert "Status: ISSUE" in line


def test_format_heartbeat_sab_running_while_game_active(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
    )
    assert "RUNNING" in line
    assert "should be paused" in line


def test_format_heartbeat_idle_no_game(daemon):
    line = daemon._format_heartbeat(
        game_name=None,
        obs_streaming=False,
        twitch_category=None,
        sab_paused=None,
    )
    assert "Idle" in line
    assert "should be" not in line


def test_format_heartbeat_sab_unreachable(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=None,
    )
    assert "Unreachable" in line


def test_print_heartbeat_calls_live_sources(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_streaming.return_value = True
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.obs.is_streaming.assert_called_once()
    daemon.twitch.get_current_game_name.assert_called_once()
    daemon.sab.is_paused.assert_called_once()
    mock_log.info.assert_called_once()


# --- Steam relaunch tests ---

STEAM_DEFAULT = r"C:\Program Files (x86)\Steam\steam.exe"
STEAM_DIR = r"C:\Program Files (x86)\Steam"


def test_ensure_steam_running_skips_when_already_running(daemon):
    mock_proc = MagicMock()
    mock_proc.name.return_value = "steam.exe"
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        with patch("daemon.subprocess.Popen") as mock_popen:
            daemon._ensure_steam_running()
            mock_popen.assert_not_called()


def test_ensure_steam_running_launches_default_exe(daemon):
    with patch("daemon.psutil.process_iter", return_value=[]):
        with patch("daemon.os.path.exists", return_value=True):
            with patch("daemon.subprocess.Popen") as mock_popen:
                daemon._ensure_steam_running()
                mock_popen.assert_called_once()
                assert mock_popen.call_args[0][0][0] == STEAM_DEFAULT


def test_ensure_steam_running_uses_config_path(daemon):
    daemon.cfg["steam"] = {"exe_path": r"D:\Steam\steam.exe"}
    with patch("daemon.psutil.process_iter", return_value=[]):
        with patch("daemon.os.path.exists", return_value=True):
            with patch("daemon.subprocess.Popen") as mock_popen:
                daemon._ensure_steam_running()
                assert mock_popen.call_args[0][0][0] == r"D:\Steam\steam.exe"


def test_ensure_steam_running_cwd_is_exe_directory(daemon):
    with patch("daemon.psutil.process_iter", return_value=[]):
        with patch("daemon.os.path.exists", return_value=True):
            with patch("daemon.subprocess.Popen") as mock_popen:
                daemon._ensure_steam_running()
                assert mock_popen.call_args[1]["cwd"] == STEAM_DIR


def test_ensure_steam_running_skips_when_exe_missing(daemon):
    with patch("daemon.psutil.process_iter", return_value=[]):
        with patch("daemon.os.path.exists", return_value=False):
            with patch("daemon.subprocess.Popen") as mock_popen:
                daemon._ensure_steam_running()
                mock_popen.assert_not_called()


def test_loop_fires_heartbeat_every_poll(daemon):
    """HEARTBEAT_EVERY=1: every poll prints heartbeat; sleep never fires (API calls throttle instead)."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True

    call_count = [0]

    def stop_after_5(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] >= 5:
            daemon._running = False

    with patch.object(daemon, "_detect_game", return_value=None), \
         patch.object(daemon, "_print_heartbeat", side_effect=stop_after_5) as mock_hb, \
         patch("daemon.time.sleep") as mock_sleep:
        daemon._running = True
        daemon._loop()

    assert mock_hb.call_count == 5
    mock_sleep.assert_not_called()
