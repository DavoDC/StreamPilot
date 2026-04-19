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
    cfg_module.load()

    try:
        import win32gui
        import win32process
        import psutil
        from twitch_client import TwitchClient
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Run: pip install pywin32 psutil")
        sys.exit(1)

    cfg = cfg_module.load()

    print("=== StreamPilot: Add Game ===")
    print("Make sure your game is running, then press Enter...")
    input()

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

    print("\nDetected windows:")
    for i, (title, cls, exe) in enumerate(windows[:20]):
        print(f"  [{i}] {exe} | {title[:60]} | {cls}")

    choice = input("\nEnter number of game window: ").strip()
    try:
        title, cls, exe = windows[int(choice)]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return

    obs_window = f"{title}:{cls}:{exe}"
    print(f"obs_window: {obs_window}")

    game_name = input("Game name (for display): ").strip()

    twitch = TwitchClient(cfg["twitch"]["client_id"], cfg["twitch"]["oauth_token"])
    results = twitch.search_game(game_name)

    if not results:
        print("No Twitch results found. Enter game ID manually.")
        game_id = input("Twitch game ID: ").strip()
    else:
        print("\nTwitch matches:")
        for i, g in enumerate(results[:10]):
            print(f"  [{i}] {g['name']} (ID: {g['id']})")
        pick = input("Select [0]: ").strip() or "0"
        game_id = results[int(pick)]["id"]

    cfg_module.add_game(exe, game_name, game_id, obs_window)
    print(f"\nAdded! Run 'streampilot start' to begin monitoring.")



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
