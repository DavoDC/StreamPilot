"""Lifecycle verbs for the dashboard process (WS-001, 003, 005, 010).

    python src/streampilot.py launch    [--port N] [--no-browser] [--no-watch]
    python src/streampilot.py preflight [--port N]
    python src/streampilot.py check     [--port N]
    python src/streampilot.py stop      [--port N]

launch    replaces any StreamPilot already on the port (found by PORT OWNER, never by command line), then starts a detached
          windowless pythonw child and returns once it answers. A foreign process on the port is never killed.
preflight prints every reason a windowless start would fail, while there is still a console to print it in.
check     prints URL, pid, boot id, sha and status. Exit 0 running, 1 not running, 2 the port is held by something else.
stop      stops the dashboard process ONLY: it asks politely (POST /quit with end_stream false) and falls back to killing the
          port owner. It never ends the stream or touches OBS and SABnzbd; stopping the stream stays a confirmed UI action (D7).

Every process, socket and HTTP call is injectable so the logic is tested without touching a real instance.
"""

import contextlib
import http.client
import importlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

DEFAULT_PORT = 8765
MIN_PYTHON = (3, 11)
MODULES = ("config", "daemon", "dashboard_server", "hot_reload", "build", "obs_client", "twitch_client", "window_safety")
OWN_HOSTS = {"127.0.0.1", "0.0.0.0", "[::1]", "[::]", "*"}
TOKEN_RE = re.compile(r'SP_TOKEN = "([^"]+)"')
QUIT_PAYLOAD = {"end_stream": False}  # the CLI never ends a stream (D7)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = 0x00000008 if os.name == "nt" else 0
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRY = os.path.join(SRC_DIR, "streampilot.py")
ROOT = os.path.abspath(os.path.join(SRC_DIR, ".."))


@dataclass
class ProcResult:
    returncode: int
    stdout: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(args, timeout=20) -> ProcResult:
    """The one place this module runs a child; no console window, never raises."""
    try:
        done = subprocess.run([str(a) for a in args], capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ProcResult(127, "")
    return ProcResult(done.returncode, done.stdout.decode("utf-8", errors="replace"))


# --- port ownership ---------------------------------------------------------

def parse_netstat(text: str, port: int) -> List[int]:
    """Pids with a LISTENING socket on port (loopback or wildcard only, so a tailnet address is never reported)."""
    pids: List[int] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[3].upper() == "LISTENING":
            host, _, prt = parts[1].rpartition(":")
            if prt == str(port) and host in OWN_HOSTS and parts[4].isdigit() and int(parts[4]) not in pids:
                pids.append(int(parts[4]))
    return pids


def listeners(port: int, run=run) -> List[int]:
    result = run(["netstat", "-ano", "-p", "TCP"])
    return parse_netstat(result.stdout, port) if result.ok else []


def kill_port_owner(port: int, own_pid: Optional[int] = None, run=run) -> List[int]:
    """Kill every process listening on port except this one. Returns the pids targeted."""
    own = os.getpid() if own_pid is None else own_pid
    targets = [p for p in listeners(port, run) if p != own]
    for pid in targets:
        run(["taskkill", "/F", "/PID", str(pid)])
    return targets


def _tcp_connect(host: str, port: int, timeout: float) -> bool:
    with socket.create_connection((host, port), timeout=timeout):
        return True


def http_json(port: int, path: str) -> Optional[dict]:
    """GET path from the local listener with a proper Host header; parsed JSON object or None."""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", path, headers={"Host": f"localhost:{port}"})
        resp = conn.getresponse()
        body = resp.read(65536)
        conn.close()
        data = json.loads(body.decode("utf-8")) if resp.status == 200 else None
    except (OSError, ValueError, http.client.HTTPException):
        return None
    return data if isinstance(data, dict) else None


def port_state(port: int, connect: Callable = _tcp_connect, fetch: Callable = http_json) -> str:
    """"free" (nothing listening), "ours" (a StreamPilot answers /api/build) or "other"."""
    try:
        connect("127.0.0.1", port, 1.0)
    except OSError:
        return "free"
    build = fetch(port, "/api/build")
    if build and build.get("app") == "StreamPilot" and "boot_id" in build:
        return "ours"
    legacy = fetch(port, "/status.json")  # started before /api/build existed
    if legacy and "build_id" in legacy and "poll_interval" in legacy:
        return "ours"
    return "other"


# --- preflight --------------------------------------------------------------

def config_problem() -> Optional[str]:
    """Why config.json cannot be loaded, or None. config.load() prints and exits on a bad file; capture that."""
    import config
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            config.load()
    except SystemExit:
        return " ".join(buf.getvalue().split()) or "config.json is invalid"
    except Exception as exc:  # noqa: BLE001  (a JSON error in a half-edited file)
        return f"config.json cannot be read: {type(exc).__name__}: {exc}"
    return None


def module_problems(modules=MODULES) -> List[str]:
    out = []
    for name in modules:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001  (ImportError, but also a SyntaxError in a half-edited module)
            out.append(f"cannot import {name}: {type(exc).__name__}: {exc}")
    return out


def preflight(port: int, state=None, config_problem=config_problem, module_problems=module_problems,
              python_version=None, holders=None) -> List[str]:
    """Every problem that would stop a start, as short sentences; empty means go."""
    state = state or port_state
    holders = holders or listeners
    problems: List[str] = []
    version = tuple(python_version) if python_version is not None else tuple(sys.version_info[:3])
    if version < MIN_PYTHON:
        problems.append(f"Python {'.'.join(map(str, MIN_PYTHON))} or newer is needed, this is {'.'.join(map(str, version))}")
    problems += module_problems()
    cp = config_problem()
    if cp:
        problems.append(cp)
    if state(port) == "other":
        pids = holders(port)
        named = f" (pid {', '.join(map(str, pids))})" if pids else ""
        problems.append(f"port {port} is held by something that is not StreamPilot{named}; "
                        f"close it or pick another port with --port N")
    return problems


# --- launch -----------------------------------------------------------------

def pythonw_for(python_exe: str) -> str:
    folder, name = os.path.split(python_exe)
    candidate = os.path.join(folder, "pythonw.exe")
    return candidate if name.lower().startswith("python") and os.path.exists(candidate) else python_exe


def child_argv(pythonw: str, entry: str, port: int, no_browser: bool = False, no_watch: bool = False) -> List[str]:
    argv = [pythonw, entry, "start", "--dashboard", "--port", str(port)]
    if not no_watch:
        argv.append("--watch")
    if no_browser:
        argv.append("--no-browser")
    return argv


def spawn(argv: List[str], popen: Callable = subprocess.Popen):
    """Detached, windowless, all three std handles on DEVNULL so a caller waiting on our pipes (Claude's Bash tool) is never held."""
    return popen(argv, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                 close_fds=True, creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))


def wait_ready(proc, port: int, timeout: float, ready: Optional[Callable] = None, sleep: Callable = time.sleep,
               clock: Callable[[], float] = time.monotonic):
    ready = ready or (lambda p: port_state(p) == "ours")
    start = clock()
    while True:
        if proc.poll() is not None:
            return False, "the dashboard process exited before it answered; see data/logs/streampilot_*.log"
        if ready(port):
            return True, ""
        if clock() - start >= timeout:
            return False, f"the dashboard did not answer on port {port} within {timeout:.0f} s; see data/logs/streampilot_*.log"
        sleep(0.25)


def _wait_free(port: int, state: Callable, sleep: Callable, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while True:
        if state(port) == "free":
            return True
        if time.monotonic() >= deadline:
            return False
        sleep(0.25)


def launch(port: int, state=None, kill=None, spawn=None, wait=None, argv=None, holders=None, sleep=time.sleep,
           ready_timeout: float = 30.0):
    """Replace any StreamPilot on the port and start a fresh detached one. Returns (exit code, message)."""
    state = state or port_state
    kill = kill or kill_port_owner
    spawn = spawn or globals()["spawn"]
    wait = wait or (lambda proc, p: wait_ready(proc, p, ready_timeout))
    holders = holders or listeners
    s = state(port)
    if s == "other":
        pids = holders(port)
        return 2, f"port {port} is held by something that is not StreamPilot (pid {', '.join(map(str, pids)) or 'unknown'}); not touching it. Use --port N."
    if s == "ours":
        kill(port)
        if not _wait_free(port, state, sleep):
            return 2, f"the old StreamPilot on port {port} did not release it"
    proc = spawn(argv)
    ok, why = wait(proc, port)
    if not ok:
        return 2, why
    return 0, f"StreamPilot is up at http://localhost:{port}/"


# --- stop -------------------------------------------------------------------

def quit_post(port: int) -> bool:
    """Ask the running dashboard to exit via POST /quit with end_stream false (the stream is left running)."""
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/", headers={"Host": f"localhost:{port}"})
        page = conn.getresponse().read().decode("utf-8", errors="replace")
        m = TOKEN_RE.search(page)
        if not m:
            return False
        conn.request("POST", "/quit", body=json.dumps(QUIT_PAYLOAD).encode("utf-8"), headers={
            "Host": f"localhost:{port}", "Origin": f"http://localhost:{port}",
            "Content-Type": "application/json", "X-StreamPilot-Token": m.group(1)})
        resp = conn.getresponse()
        resp.read()
        conn.close()
        return resp.status == 202
    except (OSError, http.client.HTTPException):
        return False


def stop(port: int, state=None, quit_post=quit_post, kill=None, sleep=time.sleep, timeout: float = 10.0):
    """Stop the dashboard process only. Returns (exit code, message)."""
    state = state or port_state
    kill = kill or kill_port_owner
    s = state(port)
    if s == "free":
        return 0, f"StreamPilot is not running on port {port}"
    if s == "other":
        return 2, f"port {port} is held by something that is not StreamPilot; not touching it"
    quit_post(port)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state(port) == "free":
            return 0, "StreamPilot stopped (stream, OBS and SABnzbd left as they were)"
        sleep(0.25)
    kill(port)
    if _wait_free(port, state, sleep, 5.0):
        return 0, "StreamPilot stopped by killing the port owner (stream, OBS and SABnzbd left as they were)"
    return 2, f"StreamPilot on port {port} would not stop"


# --- check ------------------------------------------------------------------

def check(port: int, state=None, fetch=http_json, holders=None):
    """Return (exit code, text): 0 running, 1 not running, 2 port held by something else."""
    state = state or port_state
    holders = holders or listeners
    s = state(port)
    if s == "free":
        return 1, f"not running (nothing on port {port})"
    pids = holders(port)
    if s == "other":
        return 2, f"port {port} is held by something that is not StreamPilot (pid {', '.join(map(str, pids)) or 'unknown'})"
    b = fetch(port, "/api/build") or {}  # empty for an instance older than the route
    st = (fetch(port, "/status.json") or {}).get("status", "unknown")
    pid = b.get("pid") or (pids[0] if pids else "unknown")
    return 0, "\n".join([
        f"url: http://localhost:{port}/",
        f"pid: {pid}",
        f"boot_id: {b.get('boot_id')}",
        f"build: {b.get('line')}",
        f"sha: {b.get('sha')}",
        f"status: {st}",
    ])
