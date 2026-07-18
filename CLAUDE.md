# StreamPilot - Claude Context

Python CLI daemon that auto-manages OBS streaming + SABnzbd when launching a known game.

## Key Paths

- OBS executable: `C:\Program Files\obs-studio\bin\64bit\obs64.exe`

## Problem It Solves

David manually changes two OBS settings each time he starts a game:
1. **Game Capture source** - change target exe to the current game
2. **Twitch category** - change to the matching game on Twitch

Primary use case: **Fresh start** - launch a game, stream not running - StreamPilot starts the stream, sets Game Capture + category, pauses SABnzbd

**The real purpose - psychological reassurance while gaming:** David uses a two-screen setup (game on primary/left, StreamPilot's browser dashboard on secondary/right). `run.bat` launches the daemon with no terminal window at all (via `pythonw.exe`) and opens the dashboard tab automatically - while in-game he should be able to glance right and confirm everything is handled correctly without alt-tabbing or interrupting gameplay. The goal is "I can see from one place it's all good" - stream is live, right category set, SABnzbd is paused. This is the core UX, not just automation.

Architecture: game-per-VOD
- Each game session = one VOD. Stream ends when the game closes; a fresh stream starts when the next game launches.
- Mid-session switch (keeping stream live across game changes) has been removed.

## Current OBS Setup

Single scene with two sources:
- `Application Audio Output Capture` - captures audio from a list of exes (one-time setup per new game)
- `Game Capture` - target exe changes per game (StreamPilot automates this)

## Dashboard is the source of truth (rule)

**Whenever a new feature sets or changes a Twitch/OBS setting (title, tags, category, anything else), it MUST be surfaced on the browser dashboard in the same change.** The dashboard exists so David never has to open Twitch or OBS to confirm something is set correctly - it's the single centralised view. Concretely: add the value to the daemon's dashboard-facing state (`self._current_*` in `daemon.py`, cleared in `_on_no_game`), include it in the `status_file.write_status(...)` call in `_print_heartbeat`, and add a row to `INDEX_HTML` in `dashboard_server.py` (both the static row markup and the JS `tick()` function that fills it in). Applied for Title and Tags (2026-07-18) - see `_current_title`/`_current_tags` in `daemon.py` and the Title/Tags rows in `dashboard_server.py`.

## Key Behaviour

- Polls for known game exes every 2s via `psutil`
- On game launch: updates Game Capture window target, sets Twitch category + a dynamic per-game title and tags (one PATCH, see Config section), starts stream (stopping any existing stream first for a fresh VOD), pauses SABnzbd
- On game exit: stops stream, resumes SABnzbd
- SABnzbd paused/resumed per game session only - daemon idle with no game = SABnzbd runs freely
- Unknown game: Windows toast notification - "Run 'streampilot config add-game'"
- SABnzbd unreachable: logs warning + prints prompt to pause manually
- **Heartbeat homeostasis (every 2s when game active):** verifies + self-heals all critical state - OBS WebSocket reconnect, OBS window reapply, stream restart if dropped, SABnzbd repause if drifted. Each correction shows as named field in `Status: ISSUE` line. Pattern: `observe -> compare -> correct -> flag`. Guard: stream restart only fires if `is_connected()` - prevents restart loop when OBS process is dead.
- **Dashboard (`src/dashboard_server.py`):** every heartbeat, the daemon also writes `data/state/status.json` (`src/status_file.py` - atomic write, gitignored; lives under `data/state/` not `data/logs/` since it's live runtime state, not a timestamped log). The dashboard is a tiny local web server (Python stdlib `http.server`, zero new deps, no Flask/FastAPI/Node) serving a single-file HTML/CSS/JS page that polls `/status.json` every second - opens at `http://localhost:8765/` in a browser tab, no socket/IPC coupling to the daemon, same "write state, read state" pattern as AudioManager's GUI. **Security: the handler serves exactly two routes** (`/` and `/status.json`) rather than the directory tree, so `config.json`'s secrets (OAuth token, OBS password, SABnzbd API key) can never be reached through it - never switch this to `SimpleHTTPRequestHandler`. Shows a big OK/ISSUE/IDLE/OFFLINE badge, a continuously-pulsing heartbeat dot (CSS animation - proves the page itself is alive, independent of daemon state), and Game/Category/Title/Tags/SABnzbd rows. OFFLINE (grey) fires if no fresh write within `poll_interval * 4` (min 8s) - catches a dead/crashed daemon so the dashboard never shows stale reassurance. The browser **tab title and favicon also reflect state** (colored dot + game name in the title, recolored favicon) so David can monitor by glancing at the tab without it being focused. **`run.bat` (the desktop shortcut target) always starts both** - it self-elevates (OBS game capture needs admin rights), kills any previously running `streampilot.py` instance (avoids stacking duplicates across dev restarts or repeat clicks), then runs `streampilot.py start --dashboard` via `pythonw.exe` so no console window ever appears. One click, no terminal, dashboard opens automatically.

## Stack

- Python 3.11+
- `obsws-python` - OBS WebSocket v5 (port 4455)
- `psutil` - process detection
- `requests` - Twitch API + SABnzbd API
- `pywin32` - window title/class detection for Game Capture string (used in add-game wizard)

## Config (`config/config.json`)

```json
{
  "obs": {
    "host": "localhost",
    "port": 4455,
    "password": "...",
    "game_capture_source": "Game Capture"
  },
  "twitch": {
    "client_id": "...",
    "oauth_token": "...",
    "title_template": "Davo plays {game}!",
    "base_tags": ["English", "Australia"]
  },
  "sabnzbd": {
    "enabled": true,
    "host": "localhost",
    "port": 8080,
    "api_key": "..."
  },
  "poll_interval_seconds": 2,
  "games": {
    "DeadByDaylight-Win64-Shipping.exe": {
      "name": "Dead by Daylight",
      "twitch_game_id": "17074",
      "obs_window": "Dead by Daylight  [...]:UnrealWindow:DeadByDaylight-Win64-Shipping.exe",
      "tags": ["DeadByDaylight", "Horror"]
    }
  }
}
```

`obs_window` format: `Window Title:Window Class:Executable` - generated by `add-game` wizard.

**Dynamic title and tags** (both optional, applied in the same PATCH that sets the category - no extra API calls):
- `twitch.title_template` - format string with `{game}` placeholder, applied when a game has no per-game `title`. Defaults to `Davo plays {game}!`. Truncated to Twitch's 140-char limit.
- `twitch.base_tags` - list of tags always applied, combined with each game's `tags`.
- Per game: `title` - overrides the template entirely for that game. `tags` - added on top of `base_tags`.
- Tags are sanitized to Twitch's rules: alphanumeric only, max 25 chars each, max 10 tags total, case-insensitive dedupe.

## CLI Commands

Users run `scripts/run.bat` (and `scripts/setup/add-game.bat`) - these are thin wrappers that call the Python CLI below. The table is for Claude's reference, not user instructions.

| Command | Invoked by |
|---|---|
| `pythonw src/streampilot.py start --dashboard` (daemon + dashboard, one process, no console) | `scripts/run.bat` (the desktop shortcut target) |
| `python src/streampilot.py dashboard` (reopen the dashboard tab without restarting the daemon) | manual CLI only, no `.bat` - rarely needed |
| `python src/streampilot.py config add-game` | `scripts/setup/add-game.bat` |

## Repo Structure

```
StreamPilot/
├── src/
│   ├── streampilot.py       # CLI entry point
│   ├── daemon.py            # Polling loop + state machine
│   ├── obs_client.py        # OBS WebSocket wrapper
│   ├── twitch_client.py     # Twitch API
│   ├── sabnzbd_client.py    # SABnzbd API
│   ├── status_file.py       # Daemon<->dashboard JSON contract (write/read/staleness)
│   ├── dashboard_server.py  # Local web dashboard (stdlib http.server, no deps)
│   └── config.py            # Loader + validator
├── assets/
│   ├── StreamPilotIconNoBG.ico   # Program icon (transparent background)
│   └── StreamPilotIconOriginal.png
├── config/
│   ├── config.example.json
│   └── config.json          # gitignored
├── docs/
│   ├── IDEAS.md
│   └── HISTORY.md
├── scripts/
│   ├── run.bat
│   ├── run-tests.bat
│   └── setup/
│       ├── add-game.bat
│       └── install-dependencies.bat
├── tests/
└── data/
    ├── logs/            # timestamped daemon logs
    └── state/           # status.json - live daemon<->dashboard heartbeat
```

## Target Games

Marvel Rivals and Dead by Daylight are the two primary games. Marvel Rivals is currently configured; Dead by Daylight to be added once the add-game UX is improved.

## Why This Exists (ROI Context)

The time saving (2 min manual OBS + Twitch switch) is secondary. The real value is reassurance: while gaming David doesn't want to be second-guessing whether SABnzbd is still paused or OBS is capturing the right game. StreamPilot handles it and the browser dashboard on the second screen confirms it. "I shouldn't have to think about this while I'm in a game" is the design goal. David has been burned by SABnzbd tanking stream bandwidth when forgotten - the auto-pause is a safety net, not just convenience. David also enjoys the build process and it improves his Claude workflow skills. AudioManager would have higher ROI per-session for audio workflows, but StreamPilot is near-complete so the marginal cost to finish is low.

## First-Time Setup

1. OBS: Tools > WebSocket Server Settings > enable, set port 4455 + password
2. Twitch: `streampilot auth` to get and store OAuth token
3. Fill `config/config.json` with passwords/keys
4. `streampilot config add-game` for each game (while game is running)
