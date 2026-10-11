"""Build provenance for the footer, /api/build and the launcher (WS-043, WS-045, WS-048).

Git is asked once per process (never per request, WS-034) with no console window.
BOOT_ID changes on every process start, including a hot-reload re-exec, so the
page can tell that the server behind it restarted.
"""

import os
import subprocess
import time

APP = "StreamPilot"
BOOT_ID = str(time.time())
STARTED_AT = time.time()
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_cached = None


def _git(args):
    """Run git in the repo; stdout text, or None if git cannot answer."""
    try:
        done = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, timeout=10,
                              creationflags=_CREATE_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.decode("utf-8", errors="replace") if done.returncode == 0 else None


def compute(run=_git) -> dict:
    out = run(["log", "-1", "--format=%h %cs"])
    parts = (out or "").split()
    sha, date = (parts[0], parts[1]) if len(parts) >= 2 else ("unknown", "unknown")
    dirty = bool((run(["status", "--porcelain", "--untracked-files=no"]) or "").strip())
    return {"sha": sha, "date": date, "dirty": dirty,
            "line": f"{APP} {sha} {date}" + (" +dirty" if dirty else "")}


def info() -> dict:
    """Provenance plus boot facts; cached for the life of the process."""
    global _cached
    if _cached is None:
        _cached = dict(compute(_git), app=APP, boot_id=BOOT_ID, started_at=STARTED_AT, pid=os.getpid())
    return dict(_cached)
