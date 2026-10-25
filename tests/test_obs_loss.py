"""STP-27: OBS closing, crashing or restarting while the daemon runs."""

import copy
import logging
from unittest.mock import MagicMock, patch

import pytest

import obs_client
from daemon import Daemon
from test_daemon import SAMPLE_CFG, _safe_obs_mock, _sab_mock  # noqa: F401


class FakeWS:
    """Fake obsws ReqClient: healthy until .drop() is called, then every call raises."""

    def __init__(self):
        self.dead = False
        self.calls = []

    def drop(self):
        self.dead = True

    def _call(self, name):
        self.calls.append(name)
        if self.dead:
            raise ConnectionResetError("OBS websocket closed")

    def get_version(self):
        self._call("get_version")

    def get_stream_status(self):
        self._call("get_stream_status")
        return MagicMock(output_active=True)

    def get_input_settings(self, name):
        self._call("get_input_settings")
        return MagicMock(input_settings={"window": "My Game:GameClass:game.exe"})

    def start_stream(self):
        self._call("start_stream")

    def stop_stream(self):
        self._call("stop_stream")

    def set_input_settings(self, **kw):
        self._call("set_input_settings")

    def get_input_list(self):
        self._call("get_input_list")

    def disconnect(self):
        pass


@pytest.fixture
def d(tmp_path, monkeypatch):
    monkeypatch.setattr("daemon.SAB_SETTINGS_PATH", str(tmp_path / "sab.json"))
    dm = Daemon(copy.deepcopy(SAMPLE_CFG))
    dm.twitch = MagicMock()
    dm.twitch.get_current_game_name.return_value = "My Game"
    dm.twitch.get_stream_started_at.return_value = None
    dm.sab = _sab_mock()
    dm.sab.is_paused.return_value = True
    dm.sab.is_downloading.return_value = False
    real = obs_client.OBSClient("localhost", 4455, "pw", "Game Capture")
    real._client = FakeWS()
    dm.obs = real
    return dm


def _hb(dm):
    with patch("daemon.time.sleep"):
        dm._print_heartbeat()


def test_disconnect_mid_session_does_not_crash_and_logs(d, caplog):
    d._active_game_exe = "game.exe"
    d.obs._client.drop()
    with patch.object(obs_client, "obs", MagicMock(ReqClient=MagicMock(side_effect=ConnectionRefusedError("down")))):
        with caplog.at_level(logging.WARNING):
            _hb(d)
            _hb(d)
    assert "OBS WebSocket disconnected" in caplog.text
    # no restart attempted blind while OBS is unreachable
    assert d.obs._client.calls.count("start_stream") == 0


def test_disconnect_logged_once_not_every_heartbeat(d, caplog):
    d._active_game_exe = "game.exe"
    d.obs._client.drop()
    with patch.object(obs_client, "obs", MagicMock(ReqClient=MagicMock(side_effect=ConnectionRefusedError("down")))):
        with caplog.at_level(logging.WARNING, logger="daemon"):
            for _ in range(4):
                _hb(d)
    assert caplog.text.count("OBS WebSocket disconnected") == 1


def test_reconnects_when_obs_comes_back_mid_session(d, caplog):
    d._active_game_exe = "game.exe"
    d.obs._client.drop()
    fresh = FakeWS()
    ok = MagicMock(ReqClient=MagicMock(return_value=fresh))
    with patch.object(obs_client, "obs", ok):
        with caplog.at_level(logging.INFO):
            _hb(d)
    assert d.obs._client is fresh
    assert "OBS WebSocket reconnected" in caplog.text


def test_idle_heartbeat_reconnects_after_obs_restart(d, caplog):
    d._active_game_exe = None
    d.obs._client.drop()
    fresh = FakeWS()
    with patch.object(obs_client, "obs", MagicMock(ReqClient=MagicMock(return_value=fresh))):
        with caplog.at_level(logging.INFO):
            _hb(d)
    assert d.obs._client is fresh
    assert "OBS WebSocket reconnected" in caplog.text


def test_obs_gone_at_idle_heartbeat_marks_not_streaming(d, tmp_path):
    d._active_game_exe = None
    d.obs._client.drop()
    with patch.object(obs_client, "obs", MagicMock(ReqClient=MagicMock(side_effect=ConnectionRefusedError()))):
        _hb(d)
    import json, daemon
    st = json.load(open(daemon.STATUS_PATH, encoding="utf-8"))
    assert st["streaming"] is False


def test_game_exit_after_obs_closed_still_resumes_sabnzbd(d):
    d._active_game_exe = "game.exe"
    d.obs._client.drop()
    d._on_no_game()
    d.sab.resume.assert_called_once()
