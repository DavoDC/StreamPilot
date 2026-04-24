"""StreamPilot CLI entry point."""

import argparse
import json
import logging
import os
import sys

# Ensure src/ is on path when run directly
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg_module
from daemon import Daemon

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'streampilot.log')


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def cmd_start(args):
    setup_logging()
    cfg = cfg_module.load()
    daemon = Daemon(cfg)
    daemon.start()


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
            windows.append((title, cls, exe))
        except Exception:
            pass

    win32gui.EnumWindows(_enum, None)

    if not windows:
        print("No windows found.")
        return

    choices = [
        questionary.Choice(f"{exe}  |  {title[:55]}  |  {cls}", value=i)
        for i, (title, cls, exe) in enumerate(windows[:20])
    ]
    choice = questionary.select("Select your game window:", choices=choices).ask()
    if choice is None:
        return

    title, cls, exe = windows[choice]
    obs_window = f"{title}:{cls}:{exe}"

    game_name = questionary.text(
        "Display name in StreamPilot dashboard:",
        default=title.strip(),
    ).ask()
    if not game_name:
        return
    game_name = game_name.strip()

    twitch = TwitchClient(cfg["twitch"]["client_id"], cfg["twitch"]["oauth_token"])
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

    sub.add_parser('start', help='Start background polling daemon')
    sub.add_parser('status', help='Show current game, stream state, SABnzbd state')

    config_p = sub.add_parser('config', help='Config management')
    config_sub = config_p.add_subparsers(dest='config_command', required=True)
    config_sub.add_parser('add-game', help='Wizard: detect running game and add to config')

    args = parser.parse_args()

    if args.command == 'start':
        cmd_start(args)
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'config' and args.config_command == 'add-game':
        cmd_add_game(args)


if __name__ == '__main__':
    main()
