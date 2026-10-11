"""Resolve a game's CURRENT window as an OBS 'Title:Class:Exe' string.

Some games (e.g. ARC Raiders / PioneerGame.exe) use a window class that is
random per launch, so the class stored in config.json goes stale. Asking
Windows for the live window at game start lets StreamPilot hand OBS the
current title and class; the stored string is only a fallback. OBS is also
told to match on the exe (see obs_client.py), so a stale class is harmless.
"""

import logging

import window_safety

try:
    import win32gui
    import win32process
    import psutil
except ImportError:  # non-Windows / deps missing: resolver degrades to fallback
    win32gui = None
    win32process = None
    psutil = None

log = logging.getLogger(__name__)


def _escape(part: str) -> str:
    """OBS escapes '#' and ':' inside the title and class fields."""
    return part.replace("#", "#23").replace(":", "#3A")


def find_live_window(exe: str) -> str | None:
    """Return 'Title:Class:Exe' for the first visible titled window of `exe`,
    or None if there is none (or win32 is unavailable). Never returns a
    blacklisted exe (safety: see window_safety.py)."""
    if win32gui is None or win32process is None or psutil is None:
        return None
    if window_safety.is_blacklisted(exe):
        return None
    wanted = window_safety.normalize_exe_name(exe)
    found = []

    def _enum(hwnd, _):
        if found or not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc_exe = psutil.Process(pid).name()
            if window_safety.normalize_exe_name(proc_exe) != wanted:
                return
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            return
        found.append(f"{_escape(title.strip())}:{_escape(cls)}:{proc_exe}")

    try:
        win32gui.EnumWindows(_enum, None)
    except Exception as e:
        log.warning(f"Live window lookup failed for {exe}: {e}")
        return None
    return found[0] if found else None


def resolve_obs_window(exe: str, stored: str) -> str:
    """Live window for `exe` if one exists, else the stored config string."""
    try:
        live = find_live_window(exe)
    except Exception as e:
        log.warning(f"Live window lookup failed for {exe}: {e}")
        live = None
    return live or stored
