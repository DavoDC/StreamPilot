"""CLI wiring for the lifecycle verbs (WS-010) and the start flags they rely on."""

from unittest.mock import MagicMock, patch

import streampilot


def _parse(argv):
    return streampilot.build_parser().parse_args(argv)


def test_verbs_default_to_port_8765():
    for verb in ("launch", "stop", "check", "preflight"):
        assert _parse([verb]).port == 8765


def test_port_override():
    assert _parse(["launch", "--port", "9100"]).port == 9100


def test_launch_flags():
    a = _parse(["launch", "--no-browser", "--no-watch"])
    assert a.no_browser and a.no_watch
    b = _parse(["launch"])
    assert not b.no_browser and not b.no_watch


def test_start_accepts_port_and_no_browser():
    a = _parse(["start", "--dashboard", "--port", "9001", "--no-browser"])
    assert a.port == 9001 and a.no_browser


def test_lifecycle_exit_codes_come_from_launcher():
    with patch("streampilot.launcher.stop", return_value=(0, "ok")) as m:
        assert streampilot.run_lifecycle(_parse(["stop", "--port", "9100"])) == 0
        m.assert_called_once_with(9100)
    with patch("streampilot.launcher.check", return_value=(1, "not running")):
        assert streampilot.run_lifecycle(_parse(["check"])) == 1


def test_launch_passes_flags_into_child_argv():
    with patch("streampilot.launcher.child_argv", return_value=["x"]) as argv, \
         patch("streampilot.launcher.launch", return_value=(0, "up")) as launch:
        assert streampilot.run_lifecycle(_parse(["launch", "--no-browser", "--no-watch", "--port", "9100"])) == 0
    assert argv.call_args.kwargs == {"no_browser": True, "no_watch": True}
    assert launch.call_args.args[0] == 9100
    assert launch.call_args.kwargs["argv"] == ["x"]


def test_preflight_silent_and_zero_when_clean(capsys):
    with patch("streampilot.launcher.preflight", return_value=[]):
        assert streampilot.run_lifecycle(_parse(["preflight"])) == 0
    assert capsys.readouterr().out == ""


def test_preflight_prints_each_problem_and_exits_nonzero(capsys):
    with patch("streampilot.launcher.preflight", return_value=["port 8765 is held", "no config"]):
        assert streampilot.run_lifecycle(_parse(["preflight"])) == 1
    out = capsys.readouterr().out
    assert "port 8765 is held" in out and "no config" in out


def test_cmd_start_passes_port_and_no_browser_to_dashboard():
    args = _parse(["start", "--dashboard", "--port", "9001", "--no-browser"])
    ds = MagicMock()
    thread = MagicMock()
    with patch("streampilot.setup_logging"), patch("streampilot.cfg_module.load", return_value={}), \
         patch("streampilot.Daemon", return_value=MagicMock()), patch("streampilot.os._exit"), \
         patch("threading.Thread", return_value=thread) as T, \
         patch.dict("sys.modules", {"dashboard_server": ds}):
        streampilot.cmd_start(args)
    kw = T.call_args.kwargs["kwargs"]
    assert kw["port"] == 9001 and kw["open_browser"] is False
