"""Poor-man's autoreload: watches src/ for .py changes and restarts the whole
process in place (os.execv) so ANY code change - not just HTML/CSS/JS baked
into dashboard_server.py - takes effect without a manual restart.

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


def snapshot(watch_dir: str) -> dict:
    """Return {path: mtime} for every .py file under watch_dir."""
    snap = {}
    for root, _dirs, files in os.walk(watch_dir):
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                try:
                    snap[path] = os.path.getmtime(path)
                except OSError:
                    pass
    return snap


def watch_loop(watch_dir: str, poll_interval: float = POLL_SECONDS):
    """Poll watch_dir forever; restart the process the moment any .py file's
    mtime changes. Runs until os.execv replaces the process (does not return)."""
    baseline = snapshot(watch_dir)
    while True:
        time.sleep(poll_interval)
        current = snapshot(watch_dir)
        if current != baseline:
            log.info("Code change detected under %s - restarting StreamPilot...", watch_dir)
            os.execv(sys.executable, [sys.executable] + sys.argv)


def start_watcher(watch_dir: str, poll_interval: float = POLL_SECONDS) -> threading.Thread:
    """Start the file-watcher in a background daemon thread."""
    t = threading.Thread(target=watch_loop, args=(watch_dir, poll_interval), daemon=True)
    t.start()
    log.info("Hot-reload watcher started for %s", watch_dir)
    return t
