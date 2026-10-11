"""The one health verdict (WS-091). The tray, the dashboard badge and the favicon all show this same
state, so the three can never disagree. The dashboard script mirrors the stale rule; a test pins the colours."""

import time

STALE_MULT = 4
STALE_FLOOR = 8
COLOURS = {"OK": "#3fd67a", "ISSUE": "#ff5d5d", "IDLE": "#6b7280", "OFFLINE": "#4b5563"}


def verdict(status, now=None):
    """OK / ISSUE / IDLE / OFFLINE from a status.json dict. None or a stale write is OFFLINE."""
    if not isinstance(status, dict):
        return "OFFLINE"
    now = time.time() if now is None else now
    try:
        age = now - float(status.get("timestamp") or 0)
        max_age = max(float(status.get("poll_interval") or 2) * STALE_MULT, STALE_FLOOR)
    except (TypeError, ValueError):
        return "OFFLINE"
    if age > max_age:
        return "OFFLINE"
    state = status.get("status")
    return state if state in COLOURS and state != "OFFLINE" else "IDLE"
