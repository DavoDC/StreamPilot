"""Lifecycle verbs (WS-001, 003, 005, 010): launch, stop, check, preflight, kill by port owner.
Everything touching processes, sockets or HTTP is injected, so no real instance is ever touched."""

import json

import pytest

import launcher

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       4242
  TCP    0.0.0.0:8765           0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8765         127.0.0.1:50000        ESTABLISHED     4242
  TCP    100.64.0.1:8765        0.0.0.0:0              LISTENING       999
  TCP    127.0.0.1:8766         0.0.0.0:0              LISTENING       777
  TCP    [::1]:8765             [::]:0                 LISTENING       5555
"""


def test_parse_netstat_finds_loopback_and_wildcard_listeners_only():
    assert launcher.parse_netstat(NETSTAT, 8765) == [4242, 5555]


def test_parse_netstat_ignores_other_ports_and_junk():
    assert launcher.parse_netstat(NETSTAT, 9999) == []
    assert launcher.parse_netstat("garbage\n\n", 8765) == []


class FakeRun:
    def __init__(self, netstat=NETSTAT):
        self.calls = []
        self.netstat = netstat

    def __call__(self, args, timeout=20):
        self.calls.append(list(args))
        if args[0] == "netstat":
            return launcher.ProcResult(0, self.netstat)
        return launcher.ProcResult(0, "")


def test_kill_port_owner_kills_listeners_but_never_self():
    run = FakeRun()
    killed = launcher.kill_port_owner(8765, own_pid=5555, run=run)
    assert killed == [4242]
    taskkills = [c for c in run.calls if c[0] == "taskkill"]
    assert taskkills == [["taskkill", "/F", "/PID", "4242"]]


def test_kill_port_owner_with_no_listener_kills_nothing():
    run = FakeRun(netstat="")
    assert launcher.kill_port_owner(8765, own_pid=1, run=run) == []
    assert all(c[0] != "taskkill" for c in run.calls)


# --- describe_holders: name the process holding a foreign port ---

NETSTAT_OWNER_ZERO = """
  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:8765         0.0.0.0:0              LISTENING       0
"""


class HolderRun:
    """Fake run: netstat returns netstat text; powershell (the CIM fallback) returns cim text, or raises."""

    def __init__(self, netstat, cim="", cim_raises=False):
        self.netstat = netstat
        self.cim = cim
        self.cim_raises = cim_raises
        self.calls = []

    def __call__(self, args, timeout=20):
        self.calls.append(list(args))
        if args[0] == "netstat":
            return launcher.ProcResult(0, self.netstat)
        if self.cim_raises:
            raise OSError("powershell missing")
        return launcher.ProcResult(0, self.cim)


def test_describe_holders_owner_zero_falls_back_to_cim_and_names_http_server():
    run = HolderRun(NETSTAT_OWNER_ZERO, cim="15596 python.exe python.exe -m http.server 8765\n")
    assert launcher.describe_holders(8765, run=run) == ["pid 15596 python.exe -m http.server 8765"]
    ps = [c for c in run.calls if c[0] == "powershell"]
    assert len(ps) == 1 and isinstance(ps[0], list)  # list form, never a shell string
    assert "http\\.server" in ps[0][-1] and "8765" in ps[0][-1]
    assert all(c[0] != "taskkill" for c in run.calls)  # naming never kills anything


def test_describe_holders_known_pid_names_pid_and_command_line():
    run = HolderRun(NETSTAT, cim="4242 python.exe python.exe -m streampilot\n")
    assert launcher.describe_holders(8765, run=run) == ["pid 4242 python.exe -m streampilot", "pid 5555"]
    ps = [c for c in run.calls if c[0] == "powershell"]
    assert "-in @(4242,5555)" in ps[0][-1]  # known pids are looked up by id, not by command-line guess
    assert "http" not in ps[0][-1]


def test_both_netstat_and_cim_fail_gives_old_message_without_crash():
    run = HolderRun(NETSTAT_OWNER_ZERO, cim_raises=True)
    assert launcher.describe_holders(8765, run=run) == []
    probs = launcher.preflight(8765, state=lambda p: "other", config_problem=_ok_config,
                               module_problems=lambda: [], python_version=(3, 11, 0),
                               describe=lambda p: launcher.describe_holders(p, run=run))
    assert probs == ["port 8765 is held by something that is not StreamPilot; "
                     "close it or pick another port with --port N"]


def test_preflight_message_names_the_http_server_holder():
    run = HolderRun(NETSTAT_OWNER_ZERO, cim="15596 python.exe python.exe -m http.server 8765\n")
    probs = launcher.preflight(8765, state=lambda p: "other", config_problem=_ok_config,
                               module_problems=lambda: [], python_version=(3, 11, 0),
                               describe=lambda p: launcher.describe_holders(p, run=run))
    assert probs == ["port 8765 is held by something that is not StreamPilot "
                     "(pid 15596 python.exe -m http.server 8765); close it or pick another port with --port N"]


def test_launch_message_names_holder_and_falls_back_to_pid_unknown():
    run = HolderRun(NETSTAT_OWNER_ZERO, cim="15596 python.exe python.exe -m http.server 8765\n")
    code, msg = launcher.launch(8765, state=lambda p: "other", kill=lambda p: pytest.fail("never kill foreign"),
                                spawn=lambda a: pytest.fail("never spawn over foreign"), argv=[],
                                describe=lambda p: launcher.describe_holders(p, run=run))
    assert code == 2 and "(pid 15596 python.exe -m http.server 8765)" in msg
    run_none = HolderRun(NETSTAT_OWNER_ZERO, cim_raises=True)
    code, msg = launcher.launch(8765, state=lambda p: "other", kill=lambda p: pytest.fail("never kill foreign"),
                                spawn=lambda a: pytest.fail("never spawn over foreign"), argv=[],
                                describe=lambda p: launcher.describe_holders(p, run=run_none))
    assert code == 2 and "(pid unknown)" in msg


# --- port_state ---

def _fetch_build(data):
    return lambda port, path: data if path == "/api/build" else None


def _connect_ok(host, port, timeout):
    return True


def _connect_refused(host, port, timeout):
    raise OSError("refused")


def test_port_state_free():
    assert launcher.port_state(8765, _connect_refused, _fetch_build(None)) == "free"


def test_port_state_ours():
    data = {"app": "StreamPilot", "boot_id": "1", "line": "StreamPilot x y"}
    assert launcher.port_state(8765, _connect_ok, _fetch_build(data)) == "ours"


def test_port_state_other_when_listener_is_not_streampilot():
    assert launcher.port_state(8765, _connect_ok, _fetch_build(None)) == "other"
    assert launcher.port_state(8765, _connect_ok, _fetch_build({"app": "SBS", "boot_id": "1"})) == "other"


# --- preflight ---

def _ok_config():
    return None


def test_preflight_clean():
    assert launcher.preflight(8765, state=lambda p: "free", config_problem=_ok_config,
                              module_problems=lambda: [], python_version=(3, 11, 0)) == []


def test_preflight_ours_is_fine_it_will_be_replaced():
    assert launcher.preflight(8765, state=lambda p: "ours", config_problem=_ok_config,
                              module_problems=lambda: [], python_version=(3, 11, 0)) == []


def test_preflight_port_held_by_other_names_pid_and_how_to_fix():
    probs = launcher.preflight(8765, state=lambda p: "other", config_problem=_ok_config,
                               module_problems=lambda: [], python_version=(3, 11, 0),
                               describe=lambda p: ["pid 1234"])
    assert len(probs) == 1
    assert "8765" in probs[0] and "1234" in probs[0] and "--port" in probs[0]


def test_preflight_reports_config_imports_and_old_python():
    probs = launcher.preflight(8765, state=lambda p: "free", config_problem=lambda: "config.json not found",
                               module_problems=lambda: ["cannot import psutil"], python_version=(3, 8, 0))
    text = " | ".join(probs)
    assert "config.json not found" in text
    assert "psutil" in text
    assert "Python 3.11" in text


def test_config_problem_returns_message_not_exit(monkeypatch):
    import config

    def boom():
        print("[StreamPilot] config.json not found at: x")
        raise SystemExit(1)
    monkeypatch.setattr(config, "load", boom)
    msg = launcher.config_problem()
    assert "config.json not found" in msg


def test_config_problem_none_when_load_ok(monkeypatch):
    import config
    monkeypatch.setattr(config, "load", lambda: {})
    assert launcher.config_problem() is None


# --- child argv ---

def test_child_argv_defaults_to_dashboard_and_watch():
    argv = launcher.child_argv("pythonw.exe", "src/streampilot.py", 8765)
    assert argv[:2] == ["pythonw.exe", "src/streampilot.py"]
    assert "--dashboard" in argv and "--watch" in argv
    assert argv[argv.index("--port") + 1] == "8765"
    assert "--no-browser" not in argv


def test_child_argv_flags():
    argv = launcher.child_argv("pw", "s.py", 9000, no_browser=True, no_watch=True)
    assert "--no-browser" in argv
    assert "--watch" not in argv
    assert argv[argv.index("--port") + 1] == "9000"


# --- launch ---

class FakeProc:
    def __init__(self, alive=True):
        self.alive = alive

    def poll(self):
        return None if self.alive else 1


def test_launch_kills_old_instance_spawns_and_reports_url():
    events = []
    states = iter(["ours", "ours"])
    code, msg = launcher.launch(
        8765,
        state=lambda p: "ours" if not events else "free" if events == ["kill"] else "ours",
        kill=lambda p: events.append("kill") or [4242],
        spawn=lambda argv: events.append("spawn") or FakeProc(),
        wait=lambda proc, port: (True, ""),
        argv=["pw", "s.py"],
    )
    assert code == 0
    assert events == ["kill", "spawn"]
    assert "http://localhost:8765/" in msg


def test_launch_refuses_when_port_held_by_something_else():
    events = []
    code, msg = launcher.launch(
        8765, state=lambda p: "other", kill=lambda p: events.append("kill") or [],
        spawn=lambda a: events.append("spawn"), wait=lambda *a: (True, ""), argv=[],
        describe=lambda p: ["pid 31337 python.exe -m http.server 8765"],
    )
    assert code == 2
    assert events == []  # never kills or spawns over a foreign process
    assert "pid 31337 python.exe -m http.server 8765" in msg


def test_launch_reports_failure_when_child_never_answers():
    code, msg = launcher.launch(
        8765, state=lambda p: "free", kill=lambda p: [], spawn=lambda a: FakeProc(),
        wait=lambda proc, port: (False, "did not answer"), argv=[],
    )
    assert code == 2
    assert "did not answer" in msg


def test_wait_ready_succeeds_when_ready():
    ok, _ = launcher.wait_ready(FakeProc(), 1, 5, ready=lambda p: True, sleep=lambda s: None)
    assert ok


def test_wait_ready_fails_when_process_died():
    ok, why = launcher.wait_ready(FakeProc(alive=False), 1, 5, ready=lambda p: False, sleep=lambda s: None)
    assert not ok and "exited" in why


def test_wait_ready_times_out():
    t = iter(range(0, 100, 3))
    ok, why = launcher.wait_ready(FakeProc(), 1, 5, ready=lambda p: False, sleep=lambda s: None,
                                  clock=lambda: next(t))
    assert not ok and "within" in why


# --- stop ---

def test_stop_when_not_running_is_ok():
    code, msg = launcher.stop(8765, state=lambda p: "free", quit_post=lambda p: pytest.fail("no post"),
                              kill=lambda p: pytest.fail("no kill"))
    assert code == 0
    assert "not running" in msg


def test_stop_refuses_to_touch_a_foreign_listener():
    code, msg = launcher.stop(8765, state=lambda p: "other", quit_post=lambda p: pytest.fail("no post"),
                              kill=lambda p: pytest.fail("no kill"))
    assert code == 2


def test_stop_asks_politely_and_never_ends_the_stream():
    posted = []
    seq = iter(["ours", "free"])
    code, msg = launcher.stop(8765, state=lambda p: next(seq),
                              quit_post=lambda p: posted.append(p) or True,
                              kill=lambda p: pytest.fail("no kill needed"), sleep=lambda s: None)
    assert code == 0
    assert posted == [8765]


def test_quit_payload_keeps_the_stream():
    # The CLI stop must never end the stream: stopping the stream stays a confirmed UI action (D7).
    assert launcher.QUIT_PAYLOAD == {"end_stream": False}


def test_stop_falls_back_to_kill_when_post_fails():
    killed = []
    states = iter(["ours", "ours", "ours", "free"])
    code, _ = launcher.stop(8765, state=lambda p: next(states), quit_post=lambda p: False,
                            kill=lambda p: killed.append(p) or [1], sleep=lambda s: None, timeout=0)
    assert code == 0
    assert killed == [8765]


# --- check ---

def test_check_not_running():
    code, text = launcher.check(8765, state=lambda p: "free", fetch=lambda p, path: None, holders=lambda p: [])
    assert code == 1
    assert "not running" in text


def test_check_other():
    code, text = launcher.check(8765, state=lambda p: "other", fetch=lambda p, path: None, holders=lambda p: [7])
    assert code == 2
    assert "7" in text


def test_check_ours_prints_url_pid_boot_id_sha():
    build = {"app": "StreamPilot", "boot_id": "b123", "line": "StreamPilot abc1234 2026-10-12", "sha": "abc1234", "pid": 4242}
    code, text = launcher.check(8765, state=lambda p: "ours",
                                fetch=lambda p, path: build if path == "/api/build" else {"status": "IDLE"},
                                holders=lambda p: [4242])
    assert code == 0
    for needle in ("http://localhost:8765/", "4242", "b123", "abc1234", "IDLE"):
        assert needle in text


def test_port_state_recognises_pre_build_route_instance_as_ours():
    # An instance started before /api/build existed must still be replaceable by the first new launch.
    legacy = {"status": "IDLE", "build_id": "1791746840.8", "poll_interval": 2}
    fetch = lambda port, path: legacy if path == "/status.json" else None
    assert launcher.port_state(8765, _connect_ok, fetch) == "ours"


def test_port_state_other_service_with_status_json_is_not_ours():
    fetch = lambda port, path: {"status": "ok"} if path == "/status.json" else None
    assert launcher.port_state(8765, _connect_ok, fetch) == "other"
