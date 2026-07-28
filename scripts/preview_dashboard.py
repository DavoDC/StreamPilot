"""Dev tool: preview the redesigned dashboard without touching the live
StreamPilot instance.

Serves dashboard_server on port 8766 (the live instance owns 8765 - this
script never binds it and never touches that process) and seeds a realistic
status via status_file.write_status(), the exact same JSON-status contract
the real daemon uses (see src/status_file.py, src/daemon.py's
_print_heartbeat). Writes to its own preview status file under
data/state/preview_status.json so the live dashboard's status.json is never
touched.

Usage:
    python scripts/preview_dashboard.py            # healthy streaming case
    python scripts/preview_dashboard.py --unsafe    # audio violation case
"""

import argparse
import os
import sys
import time

SRC_DIR = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, SRC_DIR)

import dashboard_server  # noqa: E402
import status_file  # noqa: E402

PREVIEW_PORT = 8766
LIVE_PORT_DO_NOT_TOUCH = 8765  # live StreamPilot instance - never bind, never kill

PREVIEW_STATUS_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'state', 'preview_status.json'
)

# Realistic healthy tag list - Twitch tags for the Palworld category, copied
# from the real status contract (src/daemon.py write_status call), not
# invented.
TAGS = [
    "English", "Australia", "Palworld", "Survival", "Crafting",
    "OpenWorld", "Creatures", "Adventure", "Multiplayer", "Pals",
]

TITLE = "Davo plays Palworld! \U0001F43D"  # emoji suffix per daemon-generated titles


def seed_status(unsafe: bool):
    """Write a preview status.json shaped exactly like status_file.write_status
    produces in production (src/daemon.py _print_heartbeat), seeding either
    the healthy streaming case or an audio-violation case."""
    if unsafe:
        audio_ok = False
        audio_exes = ["Palworld-Win64-Shipping.exe", "discord.exe"]
        audio_violations = [
            "'discord.exe' is not a known game or an allowed exe - "
            "refusing to stream with it in the audio capture list",
        ]
        status = "ISSUE"
    else:
        audio_ok = True
        audio_exes = ["Palworld-Win64-Shipping.exe"]
        audio_violations = []
        status = "OK"

    status_file.write_status(
        PREVIEW_STATUS_PATH,
        status=status,
        game="Palworld",
        streaming=True,
        category="Palworld",
        sabnzbd="Running (manual)",
        poll_interval=2,
        obs_window_ok=True,
        stream_restarted=False,
        title=TITLE,
        tags=TAGS,
        build_id=str(time.time()),
        blacklisted_window=None,
        sab_auto_manage=False,
        audio_ok=audio_ok,
        audio_violations=audio_violations,
        captured_window_title="Palworld",
        audio_exes=audio_exes,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--unsafe', action='store_true',
        help='Seed an audio VIOLATION case instead of the healthy case',
    )
    args = parser.parse_args()

    start_time = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[preview_dashboard] start time: {start_time}")
    print(f"[preview_dashboard] preview status file: {PREVIEW_STATUS_PATH}")
    print(f"[preview_dashboard] LIVE StreamPilot instance stays on port {LIVE_PORT_DO_NOT_TOUCH} - untouched")

    seed_status(unsafe=args.unsafe)
    print(f"[preview_dashboard] seeded {'UNSAFE' if args.unsafe else 'healthy'} case")

    # dashboard_server.status_json_bytes(status_path=STATUS_PATH) binds the
    # live status path as a default argument AT MODULE IMPORT TIME, and
    # Handler.do_GET() always calls it with no arguments - so reassigning
    # dashboard_server.STATUS_PATH alone would not change what gets served.
    # Rebinding __defaults__ is what actually redirects the handler to the
    # preview file instead of the live one.
    dashboard_server.STATUS_PATH = PREVIEW_STATUS_PATH
    dashboard_server.status_json_bytes.__defaults__ = (PREVIEW_STATUS_PATH,)

    url = f"http://localhost:{PREVIEW_PORT}/"
    print(f"[preview_dashboard] serving at {url}")
    print("[preview_dashboard] Press Ctrl+C to stop.")

    dashboard_server.run(port=PREVIEW_PORT, open_browser=False)


if __name__ == "__main__":
    main()
