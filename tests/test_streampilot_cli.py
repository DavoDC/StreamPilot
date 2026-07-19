"""Tests for streampilot.py's CLI wiring (argparse + cmd_start side effects).

cmd_start has real side effects (logging setup, os._exit) so these tests
mock every collaborator and just verify the --watch flag correctly starts
(or skips) the hot_reload watcher.
"""

import argparse
from unittest.mock import MagicMock, patch

import streampilot


def _parse(argv):
    parser = argparse.ArgumentParser(prog='streampilot')
    sub = parser.add_subparsers(dest='command', required=True)
    start_p = sub.add_parser('start')
    start_p.add_argument('--dashboard', action='store_true')
    start_p.add_argument('--watch', action='store_true')
    return parser.parse_args(argv)


def test_watch_flag_parses():
    args = _parse(['start', '--watch'])
    assert args.watch is True


def test_watch_flag_defaults_false():
    args = _parse(['start'])
    assert args.watch is False


def test_cmd_start_starts_watcher_when_watch_flag_set():
    args = _parse(['start', '--watch'])
    mock_daemon = MagicMock()
    with patch("streampilot.setup_logging"), \
         patch("streampilot.cfg_module.load", return_value={}), \
         patch("streampilot.Daemon", return_value=mock_daemon), \
         patch("streampilot.os._exit"), \
         patch.dict("sys.modules", {"hot_reload": MagicMock()}):
        streampilot.cmd_start(args)
        import sys
        sys.modules["hot_reload"].start_watcher.assert_called_once()


def test_cmd_start_skips_watcher_when_watch_flag_absent():
    args = _parse(['start'])
    mock_daemon = MagicMock()
    fake_hot_reload = MagicMock()
    with patch("streampilot.setup_logging"), \
         patch("streampilot.cfg_module.load", return_value={}), \
         patch("streampilot.Daemon", return_value=mock_daemon), \
         patch("streampilot.os._exit"), \
         patch.dict("sys.modules", {"hot_reload": fake_hot_reload}):
        streampilot.cmd_start(args)
    fake_hot_reload.start_watcher.assert_not_called()


def test_cmd_start_opens_browser_on_normal_launch():
    """First launch (no hot-reload restart env var) must still open the tab."""
    args = _parse(['start', '--dashboard'])
    mock_daemon = MagicMock()
    fake_hot_reload = MagicMock()
    fake_hot_reload.RESTART_ENV_VAR = "STREAMPILOT_HOT_RELOAD_RESTART"
    fake_dashboard_server = MagicMock()
    with patch("streampilot.setup_logging"), \
         patch("streampilot.cfg_module.load", return_value={}), \
         patch("streampilot.Daemon", return_value=mock_daemon), \
         patch("streampilot.os._exit"), \
         patch("threading.Thread") as mock_thread_cls, \
         patch.dict("os.environ", {}, clear=False), \
         patch.dict("sys.modules", {"hot_reload": fake_hot_reload, "dashboard_server": fake_dashboard_server}):
        import os as os_module
        os_module.environ.pop("STREAMPILOT_HOT_RELOAD_RESTART", None)
        streampilot.cmd_start(args)

    _, kwargs = mock_thread_cls.call_args
    assert kwargs["kwargs"]["open_browser"] is True


def test_cmd_start_skips_browser_on_hot_reload_restart():
    """A --watch self-restart must NOT pop open another browser tab."""
    args = _parse(['start', '--dashboard'])
    mock_daemon = MagicMock()
    fake_hot_reload = MagicMock()
    fake_hot_reload.RESTART_ENV_VAR = "STREAMPILOT_HOT_RELOAD_RESTART"
    fake_dashboard_server = MagicMock()
    with patch("streampilot.setup_logging"), \
         patch("streampilot.cfg_module.load", return_value={}), \
         patch("streampilot.Daemon", return_value=mock_daemon), \
         patch("streampilot.os._exit"), \
         patch("threading.Thread") as mock_thread_cls, \
         patch.dict("os.environ", {"STREAMPILOT_HOT_RELOAD_RESTART": "1"}), \
         patch.dict("sys.modules", {"hot_reload": fake_hot_reload, "dashboard_server": fake_dashboard_server}):
        streampilot.cmd_start(args)

    _, kwargs = mock_thread_cls.call_args
    assert kwargs["kwargs"]["open_browser"] is False
