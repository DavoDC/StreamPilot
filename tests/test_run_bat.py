"""run.bat contract (WS-001, WS-005): a thin wrapper, kills by port owner via launch, never by command line."""

import os

BAT = os.path.join(os.path.dirname(__file__), "..", "scripts", "run.bat")


def _text():
    with open(BAT, encoding="utf-8") as f:
        return f.read()


def test_run_bat_is_thin():
    assert len(_text().splitlines()) <= 40


def test_run_bat_preflights_then_launches_through_python():
    t = _text()
    assert "streampilot.py preflight" in t
    assert "streampilot.py launch" in t
    assert t.index("preflight") < t.index("streampilot.py launch")


def test_run_bat_keeps_self_elevation_and_no_command_line_kill():
    t = _text()
    assert "RunAs" in t
    assert "Get-CimInstance" not in t and "Stop-Process" not in t and "taskkill" not in t.lower()


def test_run_bat_writes_breadcrumb_before_python():
    t = _text()
    assert t.index("launch-breadcrumb.log") < t.index("\npython src")
