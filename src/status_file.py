"""JSON status contract between the daemon and the dashboard.

The daemon writes its heartbeat state here every poll; the dashboard just
reads it on a timer. No sockets, no IPC - matches AudioManager's
subprocess+JSON-contract philosophy, cheapest option for a single-user
local tool.
"""

import json
import os
import time

STALE_MULTIPLIER = 4  # no fresh write within poll_interval * this = daemon presumed dead
STALE_FLOOR_SECONDS = 8  # minimum staleness window even at very short poll intervals


def write_status(path, *, status: str, game, streaming: bool, category, sabnzbd: str, poll_interval: int, **extra):
    """Atomically write the current heartbeat state as JSON."""
    data = {
        "timestamp": time.time(),
        "status": status,
        "game": game,
        "streaming": streaming,
        "category": category,
        "sabnzbd": sabnzbd,
        "poll_interval": poll_interval,
        **extra,
    }
    path = str(path)
    tmp_path = path + ".tmp"
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)


def read_status(path):
    """Return the status dict, or None if missing/corrupt."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def is_stale(status) -> bool:
    """True if the daemon hasn't written a fresh heartbeat recently (presumed dead)."""
    if status is None:
        return True
    poll_interval = status.get("poll_interval", 2)
    max_age = max(poll_interval * STALE_MULTIPLIER, STALE_FLOOR_SECONDS)
    return (time.time() - status.get("timestamp", 0)) > max_age
