"""Fixture scenarios for the dashboard harness (WS-093): fixed, realistic status dicts shaped exactly like
status_file.write_status writes them, so the page, the capture and the contract tests exercise real shapes
without a daemon, OBS or a live stream. Fixture mode never reads or writes data/state/status.json.

The audio violation text is produced by the real audio_safety guard, so a fixture cannot drift from what the guard says.
"""

import time

import audio_safety

GAME_EXE = "Palworld-Win64-Shipping.exe"
TAGS = ["English", "Australia", "Palworld", "Survival", "Crafting", "OpenWorld", "Creatures", "Adventure", "Multiplayer", "Pals"]
TITLE = "Davo plays Palworld! \U0001F43D"
LONG_TITLE = ("Davo plays Palworld, building the biggest base the server has ever seen, then losing it all to a raid "
              "before breakfast and starting over from a single wooden pickaxe! \U0001F43D")
LONG_TAGS = TAGS + ["ChillStream", "NoBackseating", "FirstPlaythrough", "BaseBuilding", "Exploration", "Cozy"]
POLL = 2


def _violations():
    settings = {"executable_list": [{"value": GAME_EXE}, {"value": "discord.exe"}]}
    found = audio_safety.check_audio_settings(settings, {GAME_EXE})
    return [v.message for v in found], not any(v.severity == "stop" for v in found)


def _base(now):
    return {"timestamp": now, "status": "IDLE", "game": None, "streaming": False, "category": None, "sabnzbd": "Running",
            "poll_interval": POLL, "obs_window_ok": None, "stream_restarted": False, "title": None, "tags": None,
            "build_id": "fixture", "blacklisted_window": None, "sab_auto_manage": True, "audio_ok": None,
            "audio_violations": None, "captured_window_exe": None, "audio_exes": None, "stream_started_at": None}


def _live(now, title=TITLE, tags=TAGS):
    s = _base(now)
    s.update(status="OK", game="Palworld", streaming=True, category="Palworld", sabnzbd="Paused (auto)", title=title,
             tags=tags, audio_ok=True, audio_violations=[], captured_window_exe=GAME_EXE, audio_exes=[GAME_EXE],
             obs_window_ok=True, stream_started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3725)))
    return s


def _issue(now):
    s = _live(now)
    messages, ok = _violations()
    s.update(status="ISSUE", audio_ok=ok, audio_violations=messages, audio_exes=[GAME_EXE, "discord.exe"])
    return s


SCENARIOS = {
    "idle": lambda now: _base(now),
    "live": lambda now: _live(now),
    "issue": _issue,
    "offline": lambda now: None,  # no status at all: the daemon never wrote one
    "stale": lambda now: {**_live(now - 600)},  # a live-looking status the daemon stopped refreshing
    "long-title": lambda now: _live(now, LONG_TITLE, LONG_TAGS),
}


def status(name, now=None):
    """The status dict for a scenario, timestamped now. 'offline' returns the never-written default."""
    if name not in SCENARIOS:
        raise ValueError(f"unknown scenario {name!r}; choose one of: {', '.join(SCENARIOS)}")
    now = time.time() if now is None else now
    data = SCENARIOS[name](now)
    if data is None:
        data = _base(0)
    return data
