"""StreamPilot CLI entry point."""

import argparse
import json
import logging
import os
import sys
import unicodedata
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
import fixtures
import launcher
import window_safety

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs')
def _clean_title(title):
    """Display-only: games like ARC Raiders pad titles with zero-width chars (anti-scrape)."""
    out = "".join(" " if unicodedata.category(c) == "Zs" else c
                  for c in title if unicodedata.category(c) != "Cf")
    return " ".join(out.split())


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
                'port': getattr(args, 'port', None) or launcher.DEFAULT_PORT,
                'open_browser': not is_hot_reload_restart and not getattr(args, 'no_browser', False),
                'on_quit': daemon.stop,
                'twitch_channel': cfg.get('twitch', {}).get('channel_name'),
                'on_sab_toggle': daemon.set_sab_auto_manage,
                'on_restart_stream': daemon.restart_stream,
            },
            daemon=True,
        )
        t.start()
        import tray
        tray_port = getattr(args, 'port', None) or launcher.DEFAULT_PORT
        if tray.requested(tray_port):
            tray.start(tray_port, on_stop=daemon.stop, log=logging.getLogger('tray').info)
    if getattr(args, 'watch', False):
        import hot_reload
        hot_reload.add_before_restart_hook(daemon.restart_busy_reason)
        hot_reload.start_watcher(
            os.path.dirname(__file__),
            extra_files=[os.path.abspath(cfg_module.CONFIG_PATH)],
        )
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
        print("Get a new token: https://twitchtokengenerator.com (see docs/SETUP.md, Step 4)")
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
        questionary.Choice(f"{exe}  |  {_clean_title(title)[:55]}  |  {cls}", value=i)
        for i, (title, cls, exe) in enumerate(windows[:WINDOW_LIST_LIMIT])
    ]
    choice = questionary.select("Select your game window:", choices=choices).ask()
    if choice is None:
        return

    title, cls, exe = windows[choice]
    # Stored string is only a fallback (daemon sends the live window and OBS
    # matches on exe), so store the cleaned title; class stays as the OBS format needs it.
    obs_window = f"{_clean_title(title)}:{cls}:{exe}"

    game_name = questionary.text(
        "Display name in StreamPilot dashboard:",
        default=_clean_title(title),
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



def build_parser():
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
    start_p.add_argument('--port', type=int, default=launcher.DEFAULT_PORT, help='Dashboard port (default 8765)')
    start_p.add_argument('--no-browser', action='store_true', help='Do not open a browser tab')
    sub.add_parser('status', help='Show current game, stream state, SABnzbd state')
    sub.add_parser('dashboard', help='Open the live reassurance dashboard in your browser')

    launch_p = sub.add_parser('launch', help='Replace any running instance (by port owner) and start a detached windowless one')
    launch_p.add_argument('--no-browser', action='store_true', help='Do not open a browser tab')
    launch_p.add_argument('--no-watch', action='store_true', help='Start without hot reload')
    sub.add_parser('stop', help='Stop the dashboard process only (never ends the stream)')
    sub.add_parser('check', help='Print URL, pid, boot id, sha, status (exit 0 running, 1 not running, 2 port held by another program)')
    sub.add_parser('preflight', help='Print every reason a start would fail (exit 1 if any)')
    for name in ('launch', 'stop', 'check', 'preflight'):
        sub.choices[name].add_argument('--port', type=int, default=launcher.DEFAULT_PORT, help='Dashboard port (default 8765)')

    fixture_p = sub.add_parser('fixture', help='Serve a fixture scenario on a spare port (never live data, never the daemon)')
    fixture_p.add_argument('--scenario', default='live', choices=list(fixtures.SCENARIOS), help='Scenario to show (default live)')
    fixture_p.add_argument('--port', type=int, default=0, help='Port (default 0 = the OS picks a free one; the live port is refused)')
    fixture_p.add_argument('--no-browser', action='store_true', help='Do not open a browser tab')

    config_p = sub.add_parser('config', help='Config management')
    config_sub = config_p.add_subparsers(dest='config_command', required=True)
    config_sub.add_parser('add-game', help='Wizard: detect running game and add to config')
    return parser


def run_lifecycle(args) -> int:
    """Run launch/stop/check/preflight and return the process exit code."""
    port = args.port
    if args.command == 'preflight':
        problems = launcher.preflight(port)
        for p in problems:
            print(f"[FAILED] {p}")
        return 1 if problems else 0
    if args.command == 'launch':
        argv = launcher.child_argv(launcher.pythonw_for(sys.executable), launcher.ENTRY, port,
                                   no_browser=args.no_browser, no_watch=args.no_watch)
        code, msg = launcher.launch(port, argv=argv)
    elif args.command == 'stop':
        code, msg = launcher.stop(port)
    else:
        code, msg = launcher.check(port)
    print(msg)
    return code


def run_fixture(args, serve=None) -> int:
    """Serve one fixtures scenario for looking at or driving the page. Read-only and daemonless: POSTs do nothing."""
    import dashboard_server
    if args.port == launcher.DEFAULT_PORT:
        print(f"[FAILED] port {launcher.DEFAULT_PORT} is the live dashboard; fixture mode needs a spare port (use the default, 0).")
        return 2
    dashboard_server.set_fixture(args.scenario)
    server = (serve or dashboard_server.make_server)(args.port)
    url = f"http://localhost:{server.server_address[1]}/"
    print(f"[StreamPilot Fixture] scenario {args.scenario} at {url} (not live data; Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        import threading
        import webbrowser
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        dashboard_server.set_fixture(None)
    return 0


def main():
    args = build_parser().parse_args()

    if args.command == 'start':
        cmd_start(args)
    elif args.command == 'fixture':
        sys.exit(run_fixture(args))
    elif args.command in ('launch', 'stop', 'check', 'preflight'):
        sys.exit(run_lifecycle(args))
    elif args.command == 'status':
        cmd_status(args)
    elif args.command == 'dashboard':
        cmd_dashboard(args)
    elif args.command == 'config' and args.config_command == 'add-game':
        cmd_add_game(args)


if __name__ == '__main__':
    main()
