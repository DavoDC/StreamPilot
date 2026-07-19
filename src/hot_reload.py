"""Poor-man's autoreload: watches src/*.py (+ optional extra files, e.g.
config.json) and restarts the whole process in place (os.execv) so ANY
change - code or config, not just dashboard HTML/CSS/JS - takes effect
without a manual restart.

Two safety features on top of "restart on any change", both because a save
mid-edit (a half-written feature, a syntax typo) must never crash a live
process silently:
  - Debounce: a burst of edits building one feature collapses into a single
    restart once the file set has been quiet for DEBOUNCE_SECONDS, not one
    restart per keystroke/save.
  - Syntax gate: before restarting, every changed .py file must actually
    compile. A syntax error just means "not ready yet" - the watcher keeps
    the old (working) process running and re-checks each poll, instead of
    restarting into a guaranteed crash.
Neither catches every possible bug (a semantic/runtime error, or a feature
split across files where one half references a not-yet-added name, both
still only surface after the restart) - see
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
DEBOUNCE_SECONDS = 2.0

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


def watch_loop(
    watch_dir: str,
    poll_interval: float = POLL_SECONDS,
    extra_files: list = None,
    debounce_seconds: float = DEBOUNCE_SECONDS,
):
    """Poll watch_dir (+ extra_files) forever; once the file set has been
    quiet for debounce_seconds AND passes a syntax check, restart the process
    in place. Runs until os.execv replaces the process (does not return)."""
    baseline = snapshot(watch_dir, extra_files)
    previous = baseline
    stable_since = None
    while True:
        time.sleep(poll_interval)
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
        os.environ[RESTART_ENV_VAR] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)


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
