"""Config loader and validator for StreamPilot."""

import json
import os
import sys

import window_safety

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
CONFIG_EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.example.json')


def load() -> dict:
    """Load and validate config.json. Exits with helpful message if missing or invalid."""
    path = os.path.abspath(CONFIG_PATH)
    if not os.path.exists(path):
        example = os.path.abspath(CONFIG_EXAMPLE_PATH)
        print(f"[StreamPilot] config.json not found at: {path}")
        print(f"  Copy {example} to config/config.json and fill in your credentials.")
        sys.exit(1)
    with open(path, 'r') as f:
        cfg = json.load(f)
    _validate(cfg)
    return cfg


def _validate(cfg: dict):
    required = {
        'obs': ['host', 'port', 'password', 'game_capture_source'],
        'twitch': ['client_id', 'oauth_token'],
    }
    for section, keys in required.items():
        if section not in cfg:
            _fail(f"Missing section: '{section}'")
        for key in keys:
            if key not in cfg[section]:
                _fail(f"Missing key: '{section}.{key}'")
    if 'games' not in cfg or not isinstance(cfg['games'], dict):
        _fail("Missing or invalid 'games' section")

    # Safety: never let a browser/desktop/terminal window be configured as a
    # "game" - Twitch is public, streaming one of those leaks private content.
    for exe, game in cfg['games'].items():
        if window_safety.is_blacklisted(exe):
            _fail(f"'{exe}' is blacklisted (see src/window_safety.py) - refusing to stream it as a game")
        if window_safety.is_blacklisted(game.get('obs_window')):
            _fail(f"games.{exe}.obs_window resolves to a blacklisted exe - refusing to stream it")


def _fail(msg: str):
    print(f"[StreamPilot] Config error: {msg}")
    print("  Check config/config.json against config/config.example.json")
    sys.exit(1)


def add_game(exe: str, name: str, twitch_game_id: str, obs_window: str):
    """Add or update a game entry in config.json."""
    path = os.path.abspath(CONFIG_PATH)
    with open(path, 'r') as f:
        cfg = json.load(f)
    cfg.setdefault('games', {})[exe] = {
        'name': name,
        'twitch_game_id': twitch_game_id,
        'obs_window': obs_window,
    }
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f"[StreamPilot] Added game: {name} ({exe})")
