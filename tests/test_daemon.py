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
    # No base_tags or per-game tags configured -> tags omitted (None), so existing
    # Twitch tags are preserved rather than wiped by an empty list.
    daemon.twitch.set_channel_info.assert_called_once_with(
        game_id="12345", title="Davo plays My Game!", tags=None
    )
    daemon.obs.start_stream.assert_called_once()
    daemon.sab.pause.assert_called_once()


def test_on_game_launch_sets_dynamic_title_and_tags_from_config(daemon):
    """title_template, base_tags, and per-game tags are combined into set_channel_info."""
    daemon.cfg["twitch"]["title_template"] = "Now playing {game}!"
    daemon.cfg["twitch"]["base_tags"] = ["English", "Australia"]
    daemon.games["game.exe"]["tags"] = ["MarvelRivals", "Rivals"]
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.twitch.set_channel_info.assert_called_once_with(
        game_id="12345",
        title="Now playing My Game!",
        tags=["English", "Australia", "MarvelRivals", "Rivals"],
    )


def test_on_game_launch_per_game_title_override(daemon):
    daemon.games["game.exe"]["title"] = "Custom Title Here"
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    _, kwargs = daemon.twitch.set_channel_info.call_args
    assert kwargs["title"] == "Custom Title Here"


def test_on_game_launch_records_title_and_tags_for_dashboard(daemon):
    """Whatever is sent to Twitch must be readable back for the dashboard -
    David should never have to check Twitch itself to confirm it's set."""
    daemon.cfg["twitch"]["base_tags"] = ["English", "Australia"]
    daemon.games["game.exe"]["tags"] = ["MyGame"]
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    assert daemon._current_title == "Davo plays My Game!"
    assert daemon._current_tags == ["English", "Australia", "MyGame"]


def test_on_no_game_clears_dashboard_title_and_tags(daemon):
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"
    daemon._current_title = "Davo plays My Game!"
    daemon._current_tags = ["English"]
    daemon.obs.is_streaming.return_value = True

    daemon._on_no_game()

    assert daemon._current_title is None
    assert daemon._current_tags is None


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
    daemon.twitch.set_channel_info.assert_called_once()


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

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.obs.is_connected.assert_called_once()
    daemon.obs.is_streaming.assert_called_once()
    daemon.obs.get_game_capture_window.assert_called_once()
    daemon.twitch.get_current_game_name.assert_called_once()
    daemon.sab.is_paused.assert_called_once()
    mock_log.info.assert_called_once()


def test_print_heartbeat_writes_title_and_tags_to_status_file(daemon):
    """Dashboard rule: any Twitch-side setting the daemon controls must be
    written to status.json so the dashboard is the single source of truth."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"
    daemon._current_title = "Davo plays My Game!"
    daemon._current_tags = ["English", "Australia"]

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert kwargs["title"] == "Davo plays My Game!"
    assert kwargs["tags"] == ["English", "Australia"]


def test_print_heartbeat_reapplies_window_on_mismatch(daemon):
    """Heartbeat re-applies window and flags ISSUE when OBS has wrong game captured."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "Dead by Daylight  [...]:UnrealWindow:DeadByDaylight.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.obs.set_game_capture_window.assert_called_once_with("My Game:GameClass:game.exe")
    logged_line = mock_log.info.call_args[0][0]
    assert "ISSUE" in logged_line
    assert "OBS Window: REAPPLIED" in logged_line


def test_print_heartbeat_no_window_check_when_idle(daemon):
    """No game active - skip window verification entirely."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None

    daemon.obs.is_streaming.return_value = False
    daemon.twitch.get_current_game_name.return_value = None
    daemon.sab.is_paused.return_value = None

    daemon._print_heartbeat()

    daemon.obs.get_game_capture_window.assert_not_called()


def test_format_heartbeat_obs_window_wrong_shows_issue(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=True,
        obs_window_ok=False,
    )
    assert "Status: ISSUE" in line
    assert "OBS Window: REAPPLIED" in line


def test_format_heartbeat_obs_window_ok_no_extra_field(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=True,
        obs_window_ok=True,
    )
    assert "Status: OK" in line
    assert "OBS Window" not in line


def test_print_heartbeat_restarts_stream_when_stopped_during_game(daemon):
    """Stream dropped while game active and OBS WebSocket alive - stream is restarted."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = False  # stream dropped
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.obs.start_stream.assert_called_once()
    logged_line = mock_log.info.call_args[0][0]
    assert "ISSUE" in logged_line
    assert "Stream: RESTARTED" in logged_line


def test_print_heartbeat_no_stream_restart_when_obs_disconnected(daemon):
    """OBS WebSocket dead - skip stream restart (can't control a dead OBS)."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = False
    daemon.obs.connect.return_value = False  # reconnect also fails
    daemon.obs.is_streaming.return_value = False
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    daemon._print_heartbeat()

    daemon.obs.start_stream.assert_not_called()


def test_print_heartbeat_attempts_reconnect_when_obs_disconnected(daemon):
    """OBS WebSocket disconnected - reconnect is attempted."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = False
    daemon.obs.connect.return_value = True  # reconnect succeeds
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    daemon._print_heartbeat()

    daemon.obs.connect.assert_called_once()


def test_format_heartbeat_stream_restarted_shows_issue(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=False,
        twitch_category="My Game",
        sab_paused=True,
        stream_restarted=True,
    )
    assert "Status: ISSUE" in line
    assert "Stream: RESTARTED" in line


def test_format_heartbeat_stream_restarted_false_no_extra_field(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=True,
        stream_restarted=False,
    )
    assert "Stream: RESTARTED" not in line


def test_format_heartbeat_sab_corrected_shows_repaused(daemon):
    """sab_corrected=True overrides 'RUNNING' display with 'REPAUSED' and flags ISSUE."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_corrected=True,
    )
    assert "REPAUSED" in line
    assert "RUNNING" not in line
    assert "Status: ISSUE" in line


def test_format_heartbeat_sab_not_corrected_still_shows_running(daemon):
    """Without correction flag, uncorrected SABnzbd still shows 'RUNNING - should be paused'."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_corrected=False,
    )
    assert "RUNNING" in line
    assert "should be paused" in line


def test_print_heartbeat_repauses_sab_when_running_during_game(daemon):
    """SABnzbd running while game active triggers automatic re-pause."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = False  # SABnzbd has drifted - it's running

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.sab.pause.assert_called_once()
    logged_line = mock_log.info.call_args[0][0]
    assert "REPAUSED" in logged_line
    assert "ISSUE" in logged_line


def test_print_heartbeat_no_sab_correction_when_idle(daemon):
    """No game active - SABnzbd correction is skipped even if SABnzbd is running."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None

    daemon.obs.is_streaming.return_value = False
    daemon.twitch.get_current_game_name.return_value = None
    daemon.sab.is_paused.return_value = False  # running when idle is fine

    daemon._print_heartbeat()

    daemon.sab.pause.assert_not_called()


def test_print_heartbeat_no_sab_correction_when_already_paused(daemon):
    """SABnzbd already paused - no correction call made."""
    daemon.obs = MagicMock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True  # already paused - no action needed

    daemon._print_heartbeat()

    daemon.sab.pause.assert_not_called()


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


# --- get_status tests ---

def test_get_status_idle_no_connection(daemon):
    """No game, OBS not connected: active_game=None, streaming=False."""
    daemon.obs = MagicMock()
    daemon.obs._client = None        # not connected -> streaming skipped
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.sab.is_paused.return_value = False
    daemon._active_game_exe = None

    status = daemon.get_status()

    assert status["active_game"] is None
    assert status["streaming"] is False
    daemon.obs.is_streaming.assert_not_called()


def test_get_status_game_active_streaming(daemon):
    """Game running, OBS connected and streaming, SABnzbd paused."""
    daemon.obs = MagicMock()
    daemon.obs.is_streaming.return_value = True
    daemon.sab = MagicMock()
    daemon.sab.is_paused.return_value = True
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    status = daemon.get_status()

    assert status["active_game"] == "My Game"
    assert status["streaming"] is True
    assert status["sabnzbd_paused"] is True


def test_get_status_sab_disabled_returns_none(daemon):
    """sab_enabled=False -> sabnzbd_paused is None regardless of SABnzbd state."""
    daemon.obs = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = False
    daemon._active_game_exe = None

    status = daemon.get_status()

    assert status["sabnzbd_paused"] is None
    daemon.sab.is_paused.assert_not_called()


def test_get_status_obs_not_connected_returns_false_streaming(daemon):
    """OBS _client is None (not connected) -> streaming=False even with active game."""
    daemon.obs = MagicMock()
    daemon.obs._client = None
    daemon.sab = MagicMock()
    daemon.sab.is_paused.return_value = True
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    status = daemon.get_status()

    assert status["active_game"] == "My Game"
    assert status["streaming"] is False
    daemon.obs.is_streaming.assert_not_called()


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
