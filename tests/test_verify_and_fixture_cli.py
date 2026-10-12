"""verify (one PASS/FAIL line) and the `fixture` verb (spare port, never the live one)."""

import pytest

import streampilot
import verify


def test_run_all_prints_one_final_line_and_runs_every_step_after_a_failure():
    said = []
    steps = [verify.Step("a", ["a"]), verify.Step("b", ["b"]), verify.Step("c", ["c"])]
    code = verify.run_all(steps, runner=lambda cmd: 1 if cmd == ["b"] else 0, say=said.append, clock=lambda: 0.0)
    assert code == 1
    assert len(said) == 4
    assert said[-1] == "VERIFY FAIL: b (0s)"


def test_run_all_pass():
    said = []
    assert verify.run_all([verify.Step("a", ["a"])], runner=lambda c: 0, say=said.append, clock=lambda: 0.0) == 0
    assert said[-1] == "VERIFY PASS (0s)"


def test_select_rejects_unknown_step():
    with pytest.raises(SystemExit) as e:
        verify.select(["nope"])
    assert e.value.code == 2


def test_verify_runs_tests_then_capture_in_fixture_mode_only():
    names = [s.name for s in verify.STEPS]
    assert names == ["tests", "capture"]
    assert "--fixture" in verify.STEPS[1].cmd
    assert not any("--url" in s.cmd for s in verify.STEPS)


def test_fixture_verb_parses_and_defaults_to_a_spare_port():
    args = streampilot.build_parser().parse_args(["fixture"])
    assert args.command == "fixture" and args.scenario == "live" and args.port == 0


def test_fixture_verb_refuses_the_live_port(capsys):
    args = streampilot.build_parser().parse_args(["fixture", "--port", "8765"])
    assert streampilot.run_fixture(args, serve=lambda *a, **k: pytest.fail("must not bind")) == 2
    assert "8765" in capsys.readouterr().out


def test_fixture_verb_serves_the_scenario_without_the_daemon(capsys, monkeypatch):
    import dashboard_server
    seen = {}

    class FakeServer:
        server_address = ("127.0.0.1", 54321)

        def serve_forever(self):
            seen["fixture"] = dashboard_server._fixture
            raise KeyboardInterrupt

        def shutdown(self):
            seen["shutdown"] = True

        def server_close(self):
            pass

    args = streampilot.build_parser().parse_args(["fixture", "--scenario", "issue", "--no-browser"])
    assert streampilot.run_fixture(args, serve=lambda port: FakeServer()) == 0
    out = capsys.readouterr().out
    assert "http://localhost:54321/" in out and "issue" in out
    assert seen == {"fixture": "issue", "shutdown": True}
    assert dashboard_server._fixture is None  # reset after the run
