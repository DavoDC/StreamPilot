"""Config loader and validator for StreamPilot."""

import json
import os
import sys

import audio_safety
import window_safety

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
CONFIG_EXAMPLE_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.example.json')

# All keys optional - existing config.json files with no 'audio' section
# keep working untouched. See docs/HISTORY.md "Audio privacy guard".
AUDIO_DEFAULTS = {
    "source_name": "Application Audio Output Capture",
    "extra_allowed": [],
    "enforce": True,
    "auto_add_game": True,
    "require_desktop_audio_muted": True,
    "exclusive_mode": True,
}


def get_audio_config(cfg: dict) -> dict:
    """The 'audio' block merged with defaults - every key optional."""
    audio = cfg.get("audio") or {}
    return {**AUDIO_DEFAULTS, **audio}


def get_allowed_audio_exes(cfg: dict, current_game_exe: str | None = None) -> set:
    """The audio allow-list the caller should pass to
    audio_safety.check_audio_settings - audio_safety.py stays pure and
    never branches on config itself.

    exclusive_mode (default True): only the currently-streaming game plus
    audio.extra_allowed - the narrow surface. StreamPilot manages the OBS
    executable_list itself (see daemon.py convergence loop), so it can be
    exactly what's needed and nothing more; this also closes the case
    where two games happen to be running at once.

    exclusive_mode=False: the original wide list - every config.games key
    plus audio.extra_allowed - kept so this can be backed out via config
    alone, no code change.
    """
    audio = get_audio_config(cfg)
    extra = set(audio.get("extra_allowed", []))
    if audio.get("exclusive_mode", True):
        return ({current_game_exe} if current_game_exe else set()) | extra
    return set(cfg.get("games", {}).keys()) | extra


def load() -> dict:
    """Load and validate config.json. Exits with helpful message if missing or invalid."""
    path = os.path.abspath(CONFIG_PATH)
    if not os.path.exists(path):
        example = os.path.abspath(CONFIG_EXAMPLE_PATH)
        print(f"[StreamPilot] config.json not found at: {path}")
        print(f"  Copy {example} to config/config.json and fill in your credentials.")
        sys.exit(1)
    with open(path, 'r', encoding='utf-8') as f:
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

    # Same defense in depth on the audio side: even a hand-edited
    # audio.extra_allowed can never contain a hard-denied exe (Discord,
    # Chrome, etc) - see src/audio_safety.py.
    audio_cfg = cfg.get('audio') or {}
    for exe in audio_cfg.get('extra_allowed', []):
        if window_safety.normalize_exe_name(exe) in audio_safety.DENIED_EXES:
            _fail(f"audio.extra_allowed entry '{exe}' is on the audio hard-deny list (see src/audio_safety.py) - refusing to allow it")


def _fail(msg: str):
    print(f"[StreamPilot] Config error: {msg}")
    print("  Check config/config.json against config/config.example.json")
    sys.exit(1)


def add_game(exe: str, name: str, twitch_game_id: str, obs_window: str):
    """Add or update a game entry in config.json."""
    path = os.path.abspath(CONFIG_PATH)
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    cfg.setdefault('games', {})[exe] = {
        'name': name,
        'twitch_game_id': twitch_game_id,
        'obs_window': obs_window,
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    print(f"[StreamPilot] Added game: {name} ({exe})")
