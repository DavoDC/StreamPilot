"""Tests for daemon.py"""

import copy
import json
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
def daemon(tmp_path, monkeypatch):
    # Isolate from the real data/state/sab_settings.json - reading the actual
    # file (written by a real daemon run) leaked auto_manage=False into every
    # test that didn't explicitly patch SAB_SETTINGS_PATH itself, silently
    # breaking sab.pause()/resume() assertions unrelated to whatever the test
    # was actually exercising. Pre-existing bug, unrelated to the audio guard
    # work - fixed here since it blocks a clean full-suite run.
    monkeypatch.setattr("daemon.SAB_SETTINGS_PATH", str(tmp_path / "sab_settings.json"))
    return Daemon(copy.deepcopy(SAMPLE_CFG))


def _safe_obs_mock():
    """A MagicMock() for daemon.obs pre-configured with safe defaults for the
    audio privacy guard: SAMPLE_CFG's one game ('game.exe') is already in the
    capture list and no Desktop Audio/Mic inputs are reported live. Without
    this, an unconfigured get_audio_capture_settings() returns a bare
    MagicMock (not a dict), which check_audio_settings correctly treats as
    unreadable/unsafe - force-blocking every test that isn't actually
    exercising the audio guard. Tests that DO exercise the guard override
    these return values explicitly."""
    m = MagicMock()
    m.get_audio_capture_settings.return_value = {
        "executable_list": [{"hidden": False, "selected": False, "uuid": "u1", "value": "game.exe"}],
        "mode": 0,
        "exclude": False,
    }
    m.list_inputs_by_kind.return_value = []
    return m


def test_detect_game_found(daemon):
    mock_proc = MagicMock()
    mock_proc.info = {"name": "game.exe"}
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        assert daemon._detect_game() == "game.exe"


def test_detect_game_not_found(daemon):
    mock_proc = MagicMock()
    mock_proc.info = {"name": "chrome.exe"}
    with patch("daemon.psutil.process_iter", return_value=[mock_proc]):
        assert daemon._detect_game() is None


def test_detect_game_empty_process_list(daemon):
    with patch("daemon.psutil.process_iter", return_value=[]):
        assert daemon._detect_game() is None


def test_detect_game_ignores_process_with_no_name_populated(daemon):
    """A process whose attrs failed to populate (psutil drops it silently)
    must not crash the scan - simulated here as an empty/missing info dict."""
    vanished_proc = MagicMock()
    vanished_proc.info = {}
    mock_proc = MagicMock()
    mock_proc.info = {"name": "game.exe"}
    with patch("daemon.psutil.process_iter", return_value=[vanished_proc, mock_proc]):
        assert daemon._detect_game() == "game.exe"


def test_on_game_launch_starts_stream_when_not_live(daemon):
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    assert daemon._current_title == "Davo plays My Game!"
    assert daemon._current_tags == ["English", "Australia", "MyGame"]


def test_on_no_game_clears_dashboard_title_and_tags(daemon):
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    daemon.obs.stop_stream.assert_called_once()
    daemon.sab.resume.assert_called_once()


def test_on_no_game_skips_if_no_active_game(daemon):
    daemon.obs = _safe_obs_mock()
    daemon._active_game_exe = None

    daemon._on_no_game()

    daemon.obs.stop_stream.assert_not_called()


def test_on_no_game_skips_stop_if_not_streaming(daemon):
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
    daemon.obs.connect.return_value = False

    with patch("daemon.psutil.process_iter", return_value=[mock_proc]), \
         patch("daemon.subprocess.Popen"), \
         patch("daemon.time.sleep"):
        result = daemon._ensure_obs_running()

    assert result is False


def test_sab_disabled_does_not_call_sab(daemon):
    daemon.obs = _safe_obs_mock()
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
    """sab_str only reflects current truth ('Running') - no editorializing
    'should be paused' annotation, that's what the ISSUE badge is for."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
    )
    assert "Running" in line
    assert "should be paused" not in line


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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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


def test_print_heartbeat_writes_build_id_to_status_file(daemon):
    """build_id lets the dashboard detect a process restart (hot-reload or
    manual) and reload itself - must be present on every heartbeat write."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None
    daemon.obs.is_streaming.return_value = False

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert kwargs["build_id"] == daemon.build_id


def test_stop_defaults_to_ending_stream(daemon):
    daemon.stop()
    assert daemon._end_stream_on_stop is True
    assert daemon._running is False


def test_stop_can_keep_stream_running(daemon):
    daemon.stop(end_stream=False)
    assert daemon._end_stream_on_stop is False
    assert daemon._running is False


def test_reconcile_adopts_already_streaming_session(daemon):
    """Hot-reload / relaunch while a game is already live must NOT be treated
    as a fresh launch - that would stop+restart the stream and split the VOD
    for no reason."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_streaming.return_value = True
    daemon.twitch = MagicMock()
    with patch.object(daemon, "_detect_game", return_value="game.exe"):
        daemon._reconcile_existing_session()

    assert daemon._active_game_exe == "game.exe"


def test_reconcile_populates_dashboard_title_and_tags(daemon):
    """Regression: _on_game_launch() is the only other place _current_title/
    _current_tags get set. Reconcile deliberately skips _on_game_launch (that's
    what avoids restarting the stream) so it must set them itself, or the
    dashboard shows '-' for Title/Tags on every hot-reload restart."""
    daemon.cfg["twitch"]["base_tags"] = ["English"]
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_streaming.return_value = True
    daemon.twitch = MagicMock()
    with patch.object(daemon, "_detect_game", return_value="game.exe"):
        daemon._reconcile_existing_session()

    assert daemon._current_title == "Davo plays My Game!"
    assert daemon._current_tags == ["English"]


def test_reconcile_reapplies_title_tags_to_twitch(daemon):
    """A hot-reload restart must re-PATCH the freshly-built title/tags to
    Twitch itself (not just the dashboard) - e.g. an emoji/template tweak
    should take effect on the live title immediately, without waiting for
    the game to exit and relaunch. No game_id - category is untouched, and
    the stream itself is never restarted."""
    daemon.cfg["twitch"]["base_tags"] = ["English"]
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_streaming.return_value = True
    daemon.twitch = MagicMock()
    with patch.object(daemon, "_detect_game", return_value="game.exe"):
        daemon._reconcile_existing_session()

    daemon.twitch.set_channel_info.assert_called_once_with(
        title="Davo plays My Game!", tags=["English"]
    )


def test_reconcile_does_nothing_when_no_game_detected(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_streaming.return_value = True
    daemon.twitch = MagicMock()
    with patch.object(daemon, "_detect_game", return_value=None):
        daemon._reconcile_existing_session()

    assert daemon._active_game_exe is None
    daemon.twitch.set_channel_info.assert_not_called()


def test_reconcile_does_nothing_when_game_detected_but_not_streaming(daemon):
    """Game running but stream NOT live (e.g. real crash recovery) - fall
    through to the normal _loop()-driven _on_game_launch path instead."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_streaming.return_value = False
    daemon.twitch = MagicMock()
    with patch.object(daemon, "_detect_game", return_value="game.exe"):
        daemon._reconcile_existing_session()

    assert daemon._active_game_exe is None
    daemon.twitch.set_channel_info.assert_not_called()


def test_start_calls_reconcile_before_loop(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_connected.return_value = True
    daemon.sab = MagicMock()
    daemon._end_stream_on_stop = True

    with patch.object(daemon, "_ensure_steam_running"), \
         patch.object(daemon, "_ensure_obs_running", return_value=True), \
         patch.object(daemon, "_reconcile_existing_session") as mock_reconcile, \
         patch.object(daemon, "_loop"), \
         patch.object(daemon, "_on_no_game"):
        daemon.start()

    mock_reconcile.assert_called_once()


def test_start_skips_on_no_game_when_keeping_stream(daemon):
    """'Keep streaming' quit option: OBS stream and SABnzbd pause state must
    be left untouched - only the daemon loop and OBS websocket disconnect."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_connected.return_value = True
    daemon.sab = MagicMock()
    daemon._end_stream_on_stop = False

    with patch.object(daemon, "_ensure_steam_running"), \
         patch.object(daemon, "_ensure_obs_running", return_value=True), \
         patch.object(daemon, "_loop"), \
         patch.object(daemon, "_on_no_game") as mock_on_no_game:
        daemon.start()

    mock_on_no_game.assert_not_called()
    daemon.obs.disconnect.assert_called_once()


def test_start_calls_on_no_game_when_ending_stream(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.is_connected.return_value = True
    daemon.sab = MagicMock()
    daemon._end_stream_on_stop = True

    with patch.object(daemon, "_ensure_steam_running"), \
         patch.object(daemon, "_ensure_obs_running", return_value=True), \
         patch.object(daemon, "_loop"), \
         patch.object(daemon, "_on_no_game") as mock_on_no_game:
        daemon.start()

    mock_on_no_game.assert_called_once()
    daemon.obs.disconnect.assert_called_once()


def test_print_heartbeat_reapplies_window_on_mismatch(daemon):
    """Heartbeat re-applies window and flags ISSUE when OBS has wrong game captured."""
    daemon.obs = _safe_obs_mock()
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


def test_print_heartbeat_force_stops_blacklisted_window(daemon):
    """Safety: Twitch is public - if OBS's captured window is ever a browser/
    desktop/terminal, the heartbeat must force-stop the stream immediately,
    regardless of how it got there (config drift, OBS meddled with directly)."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "Google Chrome:Chrome_WidgetWin_1:chrome.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.obs.stop_stream.assert_called_once()
    daemon.obs.start_stream.assert_not_called()
    logged_line = mock_log.info.call_args[0][0]
    assert "ISSUE" in logged_line
    assert "SAFETY: BLOCKED" in logged_line
    assert "chrome.exe" in logged_line


def test_print_heartbeat_reapplies_safe_window_after_blacklist_block(daemon):
    """The force-stop must not skip the normal window-mismatch correction -
    the expected (safe) game window still gets reapplied in the same cycle."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "Explorer:CabinetWClass:explorer.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.set_game_capture_window.assert_called_once_with("My Game:GameClass:game.exe")


def test_print_heartbeat_no_blacklist_action_for_a_safe_game_window(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.stop_stream.assert_not_called()


def test_print_heartbeat_no_window_check_when_idle(daemon):
    """No game active - skip window verification entirely."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None

    daemon.obs.is_streaming.return_value = False
    daemon.twitch.get_current_game_name.return_value = None
    daemon.sab.is_paused.return_value = None

    daemon._print_heartbeat()

    daemon.obs.get_game_capture_window.assert_not_called()


def test_print_heartbeat_does_not_show_stale_category_when_idle(daemon):
    """Regression: Category must not show a leftover value (e.g. "Palworld")
    once the game has closed and Game shows "Idle" - the dashboard looked
    inconsistent/stale. Also skips the Twitch API call entirely while idle."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None

    daemon.obs.is_streaming.return_value = False
    daemon.twitch.get_current_game_name.return_value = "Palworld"  # what Twitch still reports
    daemon.sab.is_paused.return_value = None

    with patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    daemon.twitch.get_current_game_name.assert_not_called()
    _, kwargs = mock_write.call_args
    assert kwargs["category"] is None


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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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


def test_format_heartbeat_sab_corrected_shows_running(daemon):
    """sab_str only ever reflects current physical state ('Running'), whether or
    not this cycle just corrected it - sab_corrected still flags ISSUE via
    sab_issue, but no longer changes the displayed label. A one-heartbeat
    'REPAUSED' annotation used to live here; it raced the poll cycle and was
    invisible/asymmetric (no 'UNPAUSED' counterpart existed for the resume
    direction) - see docs design rule on state fields for the reasoning."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_corrected=True,
    )
    assert "Running" in line
    assert "REPAUSED" not in line
    assert "Status: ISSUE" in line


def test_format_heartbeat_sab_not_corrected_still_shows_running(daemon):
    """Without correction flag, SABnzbd still just shows 'Running' - same label
    as the corrected case, since both mean the same physical truth."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_corrected=False,
    )
    assert "Running" in line
    assert "should be paused" not in line


def test_print_heartbeat_repauses_sab_when_running_during_game(daemon):
    """SABnzbd running while game active triggers automatic re-pause."""
    daemon.obs = _safe_obs_mock()
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
    assert "Running" in logged_line
    assert "ISSUE" in logged_line


def test_format_heartbeat_sab_corrected_suppressed_shows_ok(daemon):
    """The one heartbeat right after the toggle flips on re-pauses SABnzbd
    as an expected consequence of the user's own click, not a fault -
    sab_suppress_issue keeps the badge green despite sab_corrected."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_corrected=True,
        sab_suppress_issue=True,
    )
    assert "Running" in line
    assert "Status: OK" in line


def test_set_sab_auto_manage_true_sets_just_enabled_flag(daemon):
    daemon.sab = MagicMock()
    with patch.object(daemon, "_save_sab_auto_manage"):
        daemon.set_sab_auto_manage(True)
    assert daemon._sab_just_enabled is True


def test_set_sab_auto_manage_false_does_not_set_just_enabled_flag(daemon):
    daemon.sab = MagicMock()
    with patch.object(daemon, "_save_sab_auto_manage"):
        daemon.set_sab_auto_manage(False)
    assert daemon._sab_just_enabled is False


def test_print_heartbeat_suppresses_issue_right_after_toggle_enabled(daemon):
    """Reproduces the reported flicker: toggling auto-pause ON while
    SABnzbd is running mid-game must not flash a red ISSUE badge - the
    corrective re-pause this cycle is expected, not a fault."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"
    daemon._sab_just_enabled = True

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = False

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.sab.pause.assert_called_once()
    logged_line = mock_log.info.call_args[0][0]
    assert "Running" in logged_line
    assert "Status: OK" in logged_line
    assert daemon._sab_just_enabled is False  # consumed - one-shot suppression


def test_print_heartbeat_no_sab_correction_when_idle(daemon):
    """No game active - SABnzbd correction is skipped even if SABnzbd is running."""
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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


# --- SAB auto-manage toggle tests (dashboard "idle streaming" switch) ---
# When off, StreamPilot must never pause/resume SABnzbd itself - David
# controls it manually (e.g. overnight idle streaming with a game still
# "active" but not actively played).

def _make_daemon_with_settings_path(tmp_path, initial=None):
    settings_path = tmp_path / "sab_settings.json"
    if initial is not None:
        settings_path.write_text(json.dumps(initial), encoding="utf-8")
    with patch("daemon.SAB_SETTINGS_PATH", str(settings_path)):
        d = Daemon(copy.deepcopy(SAMPLE_CFG))
    return d, settings_path


def test_sab_auto_manage_defaults_true_with_no_settings_file(tmp_path):
    d, _ = _make_daemon_with_settings_path(tmp_path)
    assert d.sab_auto_manage is True


def test_sab_auto_manage_loads_persisted_false(tmp_path):
    d, _ = _make_daemon_with_settings_path(tmp_path, initial={"auto_manage": False})
    assert d.sab_auto_manage is False


def test_sab_auto_manage_defaults_true_on_corrupt_settings_file(tmp_path):
    settings_path = tmp_path / "sab_settings.json"
    settings_path.write_text("not json", encoding="utf-8")
    with patch("daemon.SAB_SETTINGS_PATH", str(settings_path)):
        d = Daemon(copy.deepcopy(SAMPLE_CFG))
    assert d.sab_auto_manage is True


def test_set_sab_auto_manage_persists_to_file(tmp_path):
    d, settings_path = _make_daemon_with_settings_path(tmp_path)
    d.sab = MagicMock()
    with patch("daemon.SAB_SETTINGS_PATH", str(settings_path)):
        d.set_sab_auto_manage(False)
    assert json.loads(settings_path.read_text(encoding="utf-8"))["auto_manage"] is False


def test_set_sab_auto_manage_false_resumes_sab_immediately(daemon):
    """Confirmed behaviour: flipping OFF resumes SABnzbd right away instead
    of waiting for David to do it manually in SABnzbd's own UI."""
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    with patch.object(daemon, "_save_sab_auto_manage"):
        daemon.set_sab_auto_manage(False)
    daemon.sab.resume.assert_called_once()


def test_set_sab_auto_manage_true_does_not_call_resume(daemon):
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    with patch.object(daemon, "_save_sab_auto_manage"):
        daemon.set_sab_auto_manage(True)
    daemon.sab.resume.assert_not_called()


def test_on_game_launch_skips_pause_when_auto_manage_disabled(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.sab_auto_manage = False
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.sab.pause.assert_not_called()


def test_on_no_game_skips_resume_when_auto_manage_disabled(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.sab_auto_manage = False
    daemon.obs.is_streaming.return_value = True
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    daemon.sab.resume.assert_not_called()


def test_print_heartbeat_no_sab_correction_when_auto_manage_disabled(daemon):
    """SABnzbd left running during a game with auto-manage off - no repause, no ISSUE."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.sab_auto_manage = False
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = False

    with patch("daemon.log") as mock_log:
        daemon._print_heartbeat()

    daemon.sab.pause.assert_not_called()
    logged_line = mock_log.info.call_args[0][0]
    assert "ISSUE" not in logged_line


def test_print_heartbeat_writes_sab_auto_manage_to_status_file(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.sab_auto_manage = False
    daemon._active_game_exe = None
    daemon.obs.is_streaming.return_value = False

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert kwargs["sab_auto_manage"] is False


def test_format_heartbeat_sab_running_no_issue_when_auto_manage_disabled(daemon):
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_auto_manage=False,
    )
    assert "Status: ISSUE" not in line
    assert "manual" in line.lower()


def test_format_heartbeat_sab_running_still_issue_when_auto_manage_enabled(daemon):
    """Default (auto_manage=True) behaviour must be unchanged."""
    line = daemon._format_heartbeat(
        game_name="My Game",
        obs_streaming=True,
        twitch_category="My Game",
        sab_paused=False,
        sab_auto_manage=True,
    )
    assert "Status: ISSUE" in line


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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = False
    daemon._active_game_exe = None

    status = daemon.get_status()

    assert status["sabnzbd_paused"] is None
    daemon.sab.is_paused.assert_not_called()


def test_get_status_obs_not_connected_returns_false_streaming(daemon):
    """OBS _client is None (not connected) -> streaming=False even with active game."""
    daemon.obs = _safe_obs_mock()
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
    daemon.obs = _safe_obs_mock()
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


# --- Audio privacy guard integration ---

def test_check_audio_safety_safe_when_only_allowed_exe_present(daemon):
    daemon.obs = _safe_obs_mock()
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is True
    assert violations == []


def test_check_audio_safety_unsafe_unreadable_settings(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = None
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is False
    assert any(v.code == "unreadable" for v in violations)


def test_check_audio_safety_unsafe_denied_exe_present(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [
            {"value": "game.exe"},
            {"value": "discord.exe"},
        ],
    }
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is False
    assert any(v.code == "denied_exe" for v in violations)


def test_check_audio_safety_unsafe_desktop_audio_live(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.list_inputs_by_kind.side_effect = lambda kind: (
        ["Desktop Audio"] if kind == "wasapi_output_capture" else []
    )
    daemon.obs.get_input_mute.return_value = False
    daemon.obs.get_input_volume_db.return_value = -10.0

    is_safe, violations = daemon._check_audio_safety("game.exe")

    assert is_safe is False
    assert any(v.code == "desktop_audio_live" for v in violations)


def test_check_audio_safety_safe_desktop_audio_muted(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.list_inputs_by_kind.side_effect = lambda kind: (
        ["Desktop Audio"] if kind == "wasapi_output_capture" else []
    )
    daemon.obs.get_input_mute.return_value = True

    is_safe, violations = daemon._check_audio_safety("game.exe")

    assert is_safe is True
    assert violations == []


def test_check_audio_safety_ignores_desktop_leak_when_disabled(daemon):
    """audio.require_desktop_audio_muted=False skips the Desktop Audio/Mic
    check entirely - David's explicit opt-out."""
    daemon.audio_cfg["require_desktop_audio_muted"] = False
    daemon.obs = _safe_obs_mock()
    daemon.obs.list_inputs_by_kind.side_effect = lambda kind: (
        ["Desktop Audio"] if kind == "wasapi_output_capture" else []
    )
    daemon.obs.get_input_mute.return_value = False
    daemon.obs.get_input_volume_db.return_value = -10.0

    is_safe, violations = daemon._check_audio_safety("game.exe")

    assert is_safe is True
    assert violations == []
    daemon.obs.list_inputs_by_kind.assert_not_called()


def test_check_audio_safety_auto_adds_missing_game(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {"executable_list": []}

    is_safe, violations = daemon._check_audio_safety("game.exe")

    assert is_safe is True  # missing game (and empty list) are warn-only, never block
    assert any(v.code == "game_missing" for v in violations)
    daemon.obs.set_audio_capture_exes.assert_called_once_with(["game.exe"])


def test_check_audio_safety_does_not_auto_add_when_disabled(daemon):
    daemon.audio_cfg["auto_add_game"] = False
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {"executable_list": []}

    daemon._check_audio_safety("game.exe")

    daemon.obs.set_audio_capture_exes.assert_not_called()


def test_on_game_launch_preflight_blocks_start_stream_on_violation(daemon):
    """The stream must never start-then-stop - a stop violation blocks
    start_stream() from being called at all."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    with patch("daemon.log"):
        daemon._on_game_launch("game.exe")

    daemon.obs.start_stream.assert_not_called()


def test_on_game_launch_preflight_allows_start_stream_when_enforce_disabled(daemon):
    """audio.enforce=False: violations are logged but never block the stream."""
    daemon.audio_cfg["enforce"] = False
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    with patch("daemon.log"):
        daemon._on_game_launch("game.exe")

    daemon.obs.start_stream.assert_called_once()


def test_print_heartbeat_force_stops_audio_violation(daemon):
    """Mirrors the blacklisted-window force-stop: a stop-severity audio
    violation force-stops the stream every heartbeat, regardless of how it
    got there, and skips the restart-if-stopped correction that same cycle."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
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

    daemon.obs.stop_stream.assert_called_once()
    daemon.obs.start_stream.assert_not_called()
    logged_line = mock_log.info.call_args[0][0]
    assert "ISSUE" in logged_line
    assert "Audio: VIOLATION" in logged_line
    assert "Stream: RESTARTED" not in logged_line


def test_print_heartbeat_no_force_stop_when_audio_enforce_disabled(daemon):
    daemon.audio_cfg["enforce"] = False
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
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

    daemon.obs.stop_stream.assert_not_called()
    logged_line = mock_log.info.call_args[0][0]
    assert "Audio: VIOLATION" in logged_line


def test_print_heartbeat_audio_ok_shows_in_status_line(daemon):
    daemon.obs = _safe_obs_mock()
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

    logged_line = mock_log.info.call_args[0][0]
    assert "Audio: OK" in logged_line
    assert "Status: OK" in logged_line


def test_print_heartbeat_writes_audio_fields_to_status_file(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert kwargs["audio_ok"] is False
    assert any("discord.exe" in msg for msg in kwargs["audio_violations"])


def test_print_heartbeat_no_audio_check_when_idle(daemon):
    """No game active - skip the audio check entirely, mirroring the window check."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None

    daemon.obs.is_streaming.return_value = False
    daemon.twitch.get_current_game_name.return_value = None
    daemon.sab.is_paused.return_value = None

    daemon._print_heartbeat()

    daemon.obs.get_audio_capture_settings.assert_not_called()


def test_current_audio_capture_exes_returns_list(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}],
    }

    assert daemon._current_audio_capture_exes() == ["game.exe"]


def test_current_audio_capture_exes_empty_when_settings_unreadable(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = None

    assert daemon._current_audio_capture_exes() == []


def test_print_heartbeat_writes_captured_window_exe_and_audio_exes(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}],
    }
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert "captured_window_title" not in kwargs
    assert kwargs["captured_window_exe"] == "game.exe"
    assert kwargs["audio_exes"] == ["game.exe"]


def test_print_heartbeat_captured_window_exe_resolves_from_bare_exe(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    # A bare exe name (no "Title:Class:" prefix) - extract_exe still resolves it.
    assert kwargs["captured_window_exe"] == "game.exe"


def test_print_heartbeat_captured_window_exe_none_when_no_window(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = None
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"), patch("daemon.status_file.write_status") as mock_write:
        daemon._print_heartbeat()

    _, kwargs = mock_write.call_args
    assert kwargs["captured_window_exe"] is None


# --- Exclusive mode (TIER 1 - added 2026-07-28) ---
# audio.exclusive_mode defaults True: the allowed set is ONLY the current
# game + extra_allowed, not the full config.games list. StreamPilot manages
# the OBS executable_list itself, so it converges the list to exactly that
# set instead of just validating against a wide allow-list.

def test_check_audio_safety_exclusive_mode_second_game_present_is_stop(daemon):
    """A second game's exe in the capture list is a stop violation under
    exclusive mode, even though it's a perfectly valid game - only the
    CURRENTLY streaming game is allowed. Closes the two-games-at-once case."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}, {"value": "other_game.exe"}],
    }
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is False
    assert any(v.code == "unknown_exe" and "other_game.exe" in v.message for v in violations)


def test_check_audio_safety_exclusive_mode_only_current_game_is_safe(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}],
    }
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is True
    assert violations == []


def test_check_audio_safety_exclusive_mode_extra_allowed_still_permitted(daemon):
    daemon.audio_cfg["extra_allowed"] = ["voice_changer.exe"]
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}, {"value": "voice_changer.exe"}],
    }
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is True
    assert violations == []


def test_check_audio_safety_exclusive_mode_false_uses_wide_list(daemon):
    """Backed out via config alone: exclusive_mode=False restores the
    original wide allow-list (every config.games key)."""
    daemon.audio_cfg["exclusive_mode"] = False
    daemon.games["other_game.exe"] = {"name": "Other", "twitch_game_id": "1", "obs_window": "x"}
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "game.exe"}, {"value": "other_game.exe"}],
    }
    is_safe, violations = daemon._check_audio_safety("game.exe")
    assert is_safe is True
    assert violations == []


def test_on_game_launch_converges_audio_list_to_current_game(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.obs.set_audio_capture_exes.assert_any_call(["game.exe"], exact=True)


def test_on_game_launch_converges_audio_list_with_extra_allowed(daemon):
    daemon.audio_cfg["extra_allowed"] = ["voice_changer.exe"]
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    daemon.obs.set_audio_capture_exes.assert_any_call(["game.exe", "voice_changer.exe"], exact=True)


def test_on_game_launch_does_not_converge_when_exclusive_mode_false(daemon):
    daemon.audio_cfg["exclusive_mode"] = False
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = False

    daemon._on_game_launch("game.exe")

    assert call(["game.exe"], exact=True) not in daemon.obs.set_audio_capture_exes.mock_calls


def test_on_no_game_clears_audio_capture_list(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    daemon.obs.set_audio_capture_exes.assert_any_call([], exact=True)


def test_on_no_game_does_not_clear_when_exclusive_mode_false(daemon):
    daemon.audio_cfg["exclusive_mode"] = False
    daemon.obs = _safe_obs_mock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon.obs.is_streaming.return_value = True
    daemon._active_game_exe = "game.exe"

    daemon._on_no_game()

    assert call([], exact=True) not in daemon.obs.set_audio_capture_exes.mock_calls


def test_print_heartbeat_converges_audio_list_every_cycle_when_game_active(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.set_audio_capture_exes.assert_any_call(["game.exe"], exact=True)


def test_print_heartbeat_converges_audio_list_to_empty_when_idle_and_not_streaming(daemon):
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None
    daemon.obs.is_streaming.return_value = False

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.set_audio_capture_exes.assert_any_call([], exact=True)


def test_print_heartbeat_does_not_clear_audio_list_when_idle_but_still_streaming(daemon):
    """Edge case: no game detected but the stream is somehow still active -
    leave the list alone rather than blindly clearing it while live."""
    daemon.obs = _safe_obs_mock()
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = None
    daemon.obs.is_streaming.return_value = True

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.set_audio_capture_exes.assert_not_called()


def test_print_heartbeat_does_not_converge_audio_list_when_force_stopped_this_cycle(daemon):
    """CRITICAL: convergence must never be the mechanism that clears a
    flagged violation. When this cycle force-stops for an audio violation,
    the list is left exactly as the guard found it - it stays visible
    until config is fixed or the game relaunches (which re-converges via
    _on_game_launch), not silently cleaned up by the same cycle that just
    caught it."""
    daemon.obs = _safe_obs_mock()
    daemon.obs.get_audio_capture_settings.return_value = {
        "executable_list": [{"value": "discord.exe"}, {"value": "game.exe"}],
    }
    daemon.twitch = MagicMock()
    daemon.sab = MagicMock()
    daemon.sab_enabled = True
    daemon._active_game_exe = "game.exe"

    daemon.obs.is_connected.return_value = True
    daemon.obs.is_streaming.return_value = True
    daemon.obs.get_game_capture_window.return_value = "My Game:GameClass:game.exe"
    daemon.twitch.get_current_game_name.return_value = "My Game"
    daemon.sab.is_paused.return_value = True

    with patch("daemon.log"):
        daemon._print_heartbeat()

    daemon.obs.set_audio_capture_exes.assert_not_called()
