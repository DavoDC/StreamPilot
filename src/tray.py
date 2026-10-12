"""Tray icon for the dashboard (step 3, WS-011), hosted by the StreamPilot process in a daemon thread.

Menu: "Open dashboard" (left-click default), "Reload dashboard" (touches the hot-reload trigger; a live session still defers it),
a status line from the one health verdict (health.verdict, the same state the badge and favicon show; read from the dashboard's own
/status.json over loopback, so a hung server shows "Dashboard not answering") and "Quit dashboard".
Quit dashboard stops ONLY the dashboard process: it calls daemon.stop(end_stream=False), leaving the OBS stream and SABnzbd untouched.
Stopping the stream stays a confirmed UI action (decision D7), so the tray has no such item.
pystray and Pillow are optional, imported lazily: without them the dashboard runs with no icon.
STREAMPILOT_NO_TRAY=1 opts out (the test suite sets it); only the live port gets a tray; a named mutex allows one tray per session.
"""
import json
import os
import threading
import urllib.request
import webbrowser
from typing import Callable, List, Optional

import app_icon
import health
import hot_reload

REFRESH_SECONDS = 5
NO_TRAY_ENV = "STREAMPILOT_NO_TRAY"
LIVE_PORT = 8765
NOT_ANSWERING = "Dashboard not answering"
STOP_LABEL = "Quit dashboard"
RELOAD_LABEL = "Reload dashboard"
MUTEX_NAME = "Local\\StreamPilotTray"
BADGE = "#1f2937"
_mutex_handle = None


def requested(port: int, env=None) -> bool:
    env = os.environ if env is None else env
    return env.get(NO_TRAY_ENV) != "1" and int(port) == LIVE_PORT


def status_text(status, now=None) -> str:
    if status is None:
        return NOT_ANSWERING
    state = health.verdict(status, now)
    if state == "OFFLINE":
        return "Offline: no signal from the daemon"
    if state == "IDLE":
        return "Idle"
    game = status.get("game")
    label = "Issue" if state == "ISSUE" else "OK"
    return f"{label}: {game}" if game else label


def tooltip(status, now=None) -> str:
    return "StreamPilot: " + status_text(status, now)


def menu_labels(status, now=None) -> List[str]:
    return ["Open dashboard", RELOAD_LABEL, status_text(status, now), STOP_LABEL]


def request_reload(trigger_path: Optional[str] = None) -> None:
    """Touch the hot-reload trigger. Plain text, not 'force': a live game session still defers the restart."""
    path = trigger_path or hot_reload.TRIGGER_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("reload from tray")


def stop_dashboard(on_stop: Callable) -> None:
    """Stop the StreamPilot process only. end_stream=False keeps the OBS stream and SABnzbd state as they are."""
    on_stop(end_stream=False)


def fetch_status(port: int, timeout: float = 2.0):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/status.json", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def _acquire_mutex(name: str) -> bool:
    """True if this process now owns the named mutex (one tray per session). Held for the process lifetime."""
    global _mutex_handle
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.CreateMutexW(None, False, name)
        if k32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        _mutex_handle = handle
        return True
    except Exception:  # noqa: BLE001 - no windll (not Windows): allow
        return True


def _load_backend():
    try:
        import pystray
        from PIL import Image, ImageDraw
        return pystray, Image, ImageDraw
    except ImportError:
        return None


def render_icon(backend, name: str, size: int = 64):
    """The one app icon (app_icon.render, WS-130) with only a small state badge in the corner."""
    return app_icon.render(name, size)


def start(port: int, on_stop: Callable, log: Callable[[str], None] = print, fetch: Callable = fetch_status) -> bool:
    """Start the tray in a daemon thread. False (and a log line) when unavailable, already running, or it cannot start."""
    backend = _load_backend()
    if backend is None:
        log("Tray icon skipped: pystray and Pillow are not installed (pip install pystray pillow).")
        return False
    if not _acquire_mutex(MUTEX_NAME):
        log("Tray icon skipped: a StreamPilot tray is already running.")
        return False
    pystray = backend[0]
    url = f"http://localhost:{port}/"
    state = {"status": None}

    def open_dash(icon=None, item=None):
        webbrowser.open(url)

    def stop_item(icon=None, item=None):
        if icon is not None:
            icon.visible = False
        stop_dashboard(on_stop)

    def reload_item(icon=None, item=None):
        request_reload()

    menu = pystray.Menu(
        pystray.MenuItem("Open dashboard", open_dash, default=True),
        pystray.MenuItem(RELOAD_LABEL, reload_item),
        pystray.MenuItem(lambda item: status_text(state["status"]), None, enabled=False),
        pystray.MenuItem(STOP_LABEL, stop_item),
    )
    icon = pystray.Icon("StreamPilot", render_icon(backend, "OFFLINE"), "StreamPilot", menu)
    stop = threading.Event()
    # execv skips atexit, so remove the icon explicitly before a hot-reload restart (no orphan icon).
    hot_reload.add_pre_exec_hook(lambda: (stop.set(), setattr(icon, "visible", False), icon.stop()))

    def refresh():
        while not stop.is_set():
            state["status"] = fetch(port)
            icon.icon = render_icon(backend, health.verdict(state["status"]))
            icon.title = tooltip(state["status"])
            icon.update_menu()
            stop.wait(REFRESH_SECONDS)

    def runner():
        try:
            icon.run(setup=lambda i: (setattr(i, "visible", True), threading.Thread(target=refresh, daemon=True).start()))
        except Exception as exc:  # noqa: BLE001
            log(f"Tray icon stopped: {type(exc).__name__}: {exc}")

    threading.Thread(target=runner, name="streampilot-tray", daemon=True).start()
    log("Tray icon started.")
    return True
