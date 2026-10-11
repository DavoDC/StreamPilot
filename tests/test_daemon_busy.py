"""Daemon.restart_busy_reason feeds hot_reload's before-restart hook (WS-014)."""

import copy

import pytest

from daemon import Daemon
from test_daemon import SAMPLE_CFG


@pytest.fixture
def daemon(tmp_path, monkeypatch):
    monkeypatch.setattr("daemon.SAB_SETTINGS_PATH", str(tmp_path / "sab_settings.json"))
    return Daemon(copy.deepcopy(SAMPLE_CFG))


def test_idle_daemon_is_not_busy(daemon):
    daemon._active_game_exe = None
    assert daemon.restart_busy_reason() is None


def test_active_game_is_busy_and_names_the_game(daemon):
    daemon._active_game_exe = "game.exe"
    assert "My Game" in daemon.restart_busy_reason()


def test_pending_manual_restart_is_busy(daemon):
    daemon._active_game_exe = None
    daemon._manual_restart_pending = True
    assert daemon.restart_busy_reason()
