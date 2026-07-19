"""StreamPilot CLI entry point."""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# Ensure src/ is on path when run directly
sys.path.insert(0, os.path.dirname(__file__))

# pythonw.exe (used by the silent launcher, scripts/run.bat) has no console,
# so sys.stdout/stderr are None - any print() call would crash. Give them a sink.
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import config as cfg_module
from daemon import Daemon
import window_safety

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
WINDOW_LIST_LIMIT = 40  # add-game window picker cap - was 20, silently dropped windows on a busy desktop

_LOG_FMT = '[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
_DATE_FMT = '%Y-%m-%d %H:%M:%S'


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = os.path.join(LOG_DIR, f'streampilot_{timestamp}.log')
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    # sys.stdout is None under pythonw.exe (no console attached, e.g. the silent launcher) - skip console logging then
    if sys.stdout is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format=_LOG_FMT,
        datefmt=_DATE_FMT,
        handlers=handlers,
    )


def cmd_start(args):
    setup_logging()
    cfg = cfg_module.load()
    daemon = Daemon(cfg)
    if getattr(args, 'dashboard', False):
        import dashboard_server
        import hot_reload
        import threading
        # A hot-reload self-restart (--watch) carries this env var forward via
        # os.execv - only the true first launch should pop open a new browser tab.
        is_hot_reload_restart = os.environ.get(hot_reload.RESTART_ENV_VAR) == "1"
        t = threading.Thread(
            target=dashboard_server.run,
            kwargs={
                'open_browser': not is_hot_reload_restart,
                'on_quit': daemon.stop,
                'twitch_channel': cfg.get('twitch', {}).get('channel_name'),
            },
            daemon=True,
        )
        t.start()
    if getattr(args, 'watch', False):
        import hot_reload
        hot_reload.start_watcher(os.path.dirname(__file__))
    daemon.start()
    # daemon.start() only returns once the loop has stopped (dashboard Quit
    # button, or a startup failure) - os._exit guarantees the headless
    # pythonw.exe process actually terminates instead of lingering with no
    # window or console to close it from.
    os._exit(0)


def cmd_status(args):
    setup_logging()
    cfg = cfg_module.load()
    daemon = Daemon(cfg)
    if not daemon.obs.connect():
        print("[StreamPilot] Cannot connect to OBS")
        return
    status = daemon.get_status()
    print(f"Active game : {status['active_game'] or 'None'}")
    print(f"Streaming  : {status['streaming']}")
    print(f"SABnzbd    : {'paused' if status['sabnzbd_paused'] else 'running' if status['sabnzbd_paused'] is not None else 'N/A'}")
    daemon.obs.disconnect()


def cmd_dashboard(args):
    import dashboard_server
    dashboard_server.run()


def cmd_add_game(args):
    """Wizard: detect running game window, search Twitch, write to config."""
    setup_logging()

    try:
        import win32gui
        import win32process
        import psutil
        import questionary
        from twitch_client import TwitchClient
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install -r config\\requirements.txt")
        sys.exit(1)

    cfg = cfg_module.load()

    print("=== StreamPilot: Add Game ===")

    twitch = TwitchClient(cfg["twitch"]["client_id"], cfg["twitch"]["oauth_token"])
    if not twitch.validate():
        print("WARNING: Twitch token appears invalid or expired - category search below will fail.")
        print("Get a new token: https://twitchtokengenerator.com (see README Step 4)")
        print("Continuing - you can still enter a Twitch game ID manually.\n")

    windows = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            exe = proc.name()
            cls = win32gui.GetClassName(hwnd)
            # Safety: never offer a browser/desktop/terminal window as a "game" -
            # Twitch is public. See src/window_safety.py and CLAUDE.md's Safety section.
            if window_safety.is_blacklisted(exe):
                return
            windows.append((title, cls, exe))
        except Exception:
            pass

    win32gui.EnumWindows(_enum, None)

    if not windows:
        print("No windows found.")
        return

    if len(windows) > WINDOW_LIST_LIMIT:
        print(f"Note: {len(windows)} windows open, only showing the first {WINDOW_LIST_LIMIT}.")
        print("If your game isn't listed, close some other windows and try again.\n")

    choices = [
        questionary.Choice(f"{exe}  |  {title[:55]}  |  {cls}", value=i)
        for i, (title, cls, exe) in enumerate(windows[:WINDOW_LIST_LIMIT])
    ]
    choice = questionary.select("Select your game window:", choices=choices).ask()
    if choice is None:
        return

    title, cls, exe = windows[choice]
    obs_window = f"{title.strip()}:{cls}:{exe}"

    game_name = questionary.text(
        "Display name in StreamPilot dashboard:",
        default=title.strip(),
    ).ask()
    if not game_name:
        return
    game_name = game_name.strip()

    print(f'Searching Twitch for "{game_name}"...')
    results = twitch.search_game_robust(game_name)

    if not results:
        print(f'No Twitch results found for "{game_name}".')
        print("Find game IDs at: https://www.twitch.tv/directory")
        game_id = questionary.text("Enter Twitch game ID:").ask()
        if not game_id:
            return
        game_id = game_id.strip()
    else:
        twitch_choices = [
            questionary.Choice(f"{g['name']}  (ID: {g['id']})", value=g["id"])
            for g in results[:10]
        ]
        game_id = questionary.select("Select Twitch category:", choices=twitch_choices).ask()
        if game_id is None:
            return

    cfg_module.add_game(exe, game_name, game_id, obs_window)
    print(f"\nAdded! Run scripts\\run.bat to begin monitoring.")



def main():
    parser = argparse.ArgumentParser(
        prog='streampilot',
        description='StreamPilot - auto-manage OBS streaming when games launch',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    start_p = sub.add_parser('start', help='Start background polling daemon')
    start_p.add_argument('--dashboard', action='store_true', help='Also open the live dashboard in your browser')
    start_p.add_argument(
        '--watch', action='store_true',
        help='Dev mode: auto-restart on any source code change (src/*.py), dashboard tab reloads itself too'
    )
    sub.add_parser('status', help='Show current game, stream state, SABnzbd state')
    sub.add_parser('dashboard', help='Open the live reassurance dashboard in your browser')

    config_p = sub.add_parser('config', help='Config management')
    config_sub = config_p.add_subparsers(dest='config_command', required=True)
    config_sub.add_parser('add-game', help='Wizard: detect running game and add to config')

    args = parser.parse_args()

    if args.command == 'start':
        cmd_start(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'dashboard':
        cmd_dashboard(args)
    elif args.command == 'config' and args.config_command == 'add-game':
        cmd_add_game(args)


if __name__ == '__main__':
    main()
