"""Poor-man's autoreload: watches src/*.py (+ optional extra files, e.g.
config.json) and restarts the whole process in place (os.execv) so ANY
change - code or config, not just dashboard HTML/CSS/JS - takes effect
without a manual restart.

Two ways a restart gets triggered:
  - Explicit signal (preferred for a deliberate multi-file/multi-minute
    feature build): touch TRIGGER_PATH and the very next poll restarts
    immediately (after a syntax check) - no waiting around. This is the
    "I want to reload now" signal - simplest possible IPC, a marker file,
    no sockets/ports.
  - Passive fallback (for a quick one-line edit nobody explicitly signals):
    once the watched file set has gone quiet for DEBOUNCE_SECONDS (long by
    design - see below), it restarts on its own.

Why the passive fallback is a LONG debounce, not a short one: a real feature
build is a series of edits across a few minutes, with pauses (reading a
file, thinking, running tests) well over a couple of seconds. A short
debounce would auto-restart mid-build into syntax-valid-but-half-wired code
- exactly the failure mode a deliberate signal avoids. The explicit trigger
is the fast path; the long passive debounce only exists so a change is never
stuck forever if nobody remembers to signal.

Either way, before actually restarting: every changed .py file must compile
(check_syntax()) - a syntax error just means "not ready yet", the watcher
logs a warning and keeps the old (working) process running, re-checking
each poll, instead of restarting into a guaranteed crash. This does NOT
catch a semantic/runtime bug (a feature that's syntax-valid but wired wrong,
or the psutil-race class of bug from earlier) - see
feedback_live_process_hotreload_verify_liveness.md for the verification
discipline that covers the rest.

Opt-in via `streampilot start --watch`. Never runs during a normal streaming
session unless explicitly requested - stdlib only, no watchdog dependency,
matches the dashboard's zero-new-deps philosophy.
"""

import logging
import os
import sys
import threading
import time

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0
# Long on purpose - the explicit trigger (touch TRIGGER_PATH) is the fast
# path; this is only a lazy safety net for changes nobody signals.
DEBOUNCE_SECONDS = 30.0

# Touch this file to reload immediately (checked every poll, consumed/deleted
# on read). Lives beside status.json - same "simple local state file"
# convention, no new directory needed (data/state/ already exists by the
# time the daemon has written its first heartbeat).
TRIGGER_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'reload.trigger')

# Set on os.environ right before a self-restart, inherited by the re-exec'd
# process automatically (execv carries the current env forward). streampilot.py
# reads this to skip re-opening a browser tab on every hot-reload restart -
# only the true first launch should do that.
RESTART_ENV_VAR = "STREAMPILOT_HOT_RELOAD_RESTART"


def snapshot(watch_dir: str, extra_files: list = None) -> dict:
    """Return {path: mtime} for every .py file under watch_dir, plus any
    extra_files (e.g. config.json - not under watch_dir and not .py, but
    still worth reacting to)."""
    snap = {}
    for root, _dirs, files in os.walk(watch_dir):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    pass
    for path in (extra_files or []):
        try:
            snap[path] = os.path.getmtime(path)
        except OSError:
            pass
    return snap


def check_syntax(watch_dir: str) -> tuple:
    """Compile-check every .py file under watch_dir (in memory only - the
    builtin compile() has no bytecode-cache side effect, unlike py_compile).
    Returns (True, None) if all valid, else (False, "path: error")."""
    for root, _dirs, files in os.walk(watch_dir):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        source = f.read()
                    compile(source, path, "exec")
                except SyntaxError as e:
                    return False, f"{path}: {e}"
                except OSError:
                    pass
    return True, None


def _restart():
    os.environ[RESTART_ENV_VAR] = "1"
    os.execv(sys.executable, [sys.executable] + sys.argv)


def _check_trigger(watch_dir: str, trigger_path: str) -> bool:
    """If trigger_path exists, consume it (delete) and restart immediately -
    after a syntax check - regardless of debounce state. Returns True if it
    handled a trigger (whether or not that led to an actual restart), so the
    caller can skip the normal debounce logic for this poll."""
    if not os.path.exists(trigger_path):
        return False
    try:
        os.remove(trigger_path)
    except OSError:
        pass
    ok, error = check_syntax(watch_dir)
    if not ok:
        log.warning("Reload triggered but not restarting - syntax error: %s", error)
        return True
    log.info("Reload triggered explicitly (%s) - restarting StreamPilot...", trigger_path)
    _restart()
    return True  # unreachable after a real restart; kept for clarity/tests


def watch_loop(
    watch_dir: str,
    poll_interval: float = POLL_SECONDS,
    extra_files: list = None,
    debounce_seconds: float = DEBOUNCE_SECONDS,
    trigger_path: str = None,
):
    """Poll watch_dir (+ extra_files) forever. Restarts either immediately on
    an explicit trigger-file signal, or after the file set has been quiet for
    debounce_seconds (the passive fallback) - both gated by a syntax check.
    Runs until os.execv replaces the process (does not return)."""
    trigger_path = trigger_path or TRIGGER_PATH
    baseline = snapshot(watch_dir, extra_files)
    previous = baseline
    stable_since = None
    while True:
        time.sleep(poll_interval)

        if _check_trigger(watch_dir, trigger_path):
            continue

        current = snapshot(watch_dir, extra_files)

        if current == baseline:
            stable_since = None
            previous = current
            continue

        if current != previous:
            # still actively changing - reset the quiet-period timer
            stable_since = time.time()
            previous = current
            continue

        if stable_since is None or (time.time() - stable_since) < debounce_seconds:
            continue

        ok, error = check_syntax(watch_dir)
        if not ok:
            log.warning("Change detected but not restarting - syntax error: %s", error)
            continue

        log.info("Code change detected under %s - restarting StreamPilot...", watch_dir)
        _restart()


def start_watcher(
    watch_dir: str,
    poll_interval: float = POLL_SECONDS,
    extra_files: list = None,
) -> threading.Thread:
    """Start the file-watcher in a background daemon thread."""
    t = threading.Thread(
        target=watch_loop, args=(watch_dir, poll_interval, extra_files), daemon=True
    )
    t.start()
    log.info("Hot-reload watcher started for %s (+ %d extra file(s))", watch_dir, len(extra_files or []))
    return t
