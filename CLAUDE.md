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

## Safety: never stream a non-game window (rule, added 2026-07-19)

**Twitch is completely public. StreamPilot must never let OBS's Game Capture window
resolve to a browser, the raw desktop, or a terminal/editor** - any of those could leak
private tabs, files, or credentials to the whole audience. Enforced in three places
(`src/window_safety.py` is the single shared blacklist all three read from - extend the
list there, never duplicate it):
1. **Config validation** (`config.py::_validate`) - daemon refuses to start if any
   `games` entry's exe key or `obs_window` resolves to a blacklisted exe.
2. **add-game wizard** (`streampilot.py::cmd_add_game`) - refuses to save a blacklisted
   window, before it ever reaches config.json.
3. **Live heartbeat check** (`daemon.py::_print_heartbeat`, the important one) - reads
   OBS's ACTUAL current Game Capture window every cycle and force-stops the stream
   immediately if it's ever blacklisted, regardless of how it got there (config edited
   by hand, OBS meddled with directly, a future bug elsewhere). The normal window-mismatch
   correction then reapplies the expected (safe) game window in the same cycle; the
   stream-restart-if-stopped correction is skipped for that cycle so it doesn't
   immediately undo the force-stop.
Default blacklist: common browsers (chrome/edge/firefox/brave/opera/iexplore), raw
desktop (explorer.exe, dwm.exe), terminals/editors (cmd/powershell/pwsh/WindowsTerminal/
notepad/Code), and OBS itself (obs64/obs32 - capturing OBS's own window is a meaningless
mirror loop).

## Dashboard is the source of truth (rule)

**Whenever a new feature sets or changes a Twitch/OBS setting (title, tags, category, anything else), it MUST be surfaced on the browser dashboard in the same change.** The dashboard exists so David never has to open Twitch or OBS to confirm something is set correctly - it's the single centralised view. Concretely: add the value to the daemon's dashboard-facing state (`self._current_*` in `daemon.py`, cleared in `_on_no_game`), include it in the `status_file.write_status(...)` call in `_print_heartbeat`, and add a row to `INDEX_HTML` in `dashboard_server.py` (both the static row markup and the JS `tick()` function that fills it in). Applied for Title and Tags (2026-07-18) - see `_current_title`/`_current_tags` in `daemon.py` and the Title/Tags rows in `dashboard_server.py`.

## Key Behaviour

- Polls for known game exes every 2s via `psutil`
- On game launch: updates Game Capture window target, sets Twitch category + a dynamic per-game title and tags (one PATCH, see Config section), starts stream (stopping any existing stream first for a fresh VOD), pauses SABnzbd
- On game exit: stops stream, resumes SABnzbd
- SABnzbd paused/resumed per game session only - daemon idle with no game = SABnzbd runs freely
- Unknown/unconfigured game: `_detect_game()` only matches exes already in `config.games`, so an unrecognised process is silently ignored - no notification today (corrected 2026-07-21; this line previously claimed a Windows toast exists, but no such code is in `src/`). Run `streampilot config add-game` manually while it's running. A real toast notification is tracked as an open idea in `docs/IDEAS.md` (Medium priority).
- SABnzbd unreachable: logs warning + prints prompt to pause manually
- **Heartbeat homeostasis (every 2s when game active):** verifies + self-heals all critical state - OBS WebSocket reconnect, OBS window reapply, stream restart if dropped, SABnzbd repause if drifted. Each correction shows as named field in `Status: ISSUE` line. Pattern: `observe -> compare -> correct -> flag`. Guard: stream restart only fires if `is_connected()` - prevents restart loop when OBS process is dead.
- **Dashboard (`src/dashboard_server.py`):** every heartbeat, the daemon also writes `data/state/status.json` (`src/status_file.py` - atomic write, gitignored; lives under `data/state/` not `data/logs/` since it's live runtime state, not a timestamped log). The dashboard is a tiny local web server (Python stdlib `http.server`, zero new deps, no Flask/FastAPI/Node) serving a single-file HTML/CSS/JS page that polls `/status.json` every second - opens at `http://localhost:8765/` in a browser tab, no socket/IPC coupling to the daemon, same "write state, read state" pattern as AudioManager's GUI. **Security: the handler serves exactly two routes** (`/` and `/status.json`) rather than the directory tree, so `config.json`'s secrets (OAuth token, OBS password, SABnzbd API key) can never be reached through it - never switch this to `SimpleHTTPRequestHandler`. Shows a big OK/ISSUE/IDLE/OFFLINE badge, a continuously-pulsing heartbeat dot (CSS animation - proves the page itself is alive, independent of daemon state), and Game/Category/Title/Tags/SABnzbd rows, plus a "Watch on Twitch ↗" link
(`twitch.channel_name` in config - see the Config section). OFFLINE (grey) fires if no fresh write within `poll_interval * 4` (min 8s) - catches a dead/crashed daemon so the dashboard never shows stale reassurance. The browser **tab title and favicon also reflect state** (colored dot + game name in the title, recolored favicon) so David can monitor by glancing at the tab without it being focused. **`run.bat` (the desktop shortcut target) always starts both** - it self-elevates (OBS game capture needs admin rights), kills any previously running `streampilot.py` instance (avoids stacking duplicates across dev restarts or repeat clicks), then runs `streampilot.py start --dashboard --watch` via `pythonw.exe` so no console window ever appears (hot-reload on by default - see "Dev mode: hot-reload"). One click, no terminal, dashboard opens automatically. **Quit button** opens a 3-option dialog - Cancel, "Keep streaming" (`end_stream: false`: closes StreamPilot only, OBS stream and SABnzbd pause state untouched), "End stream" (`end_stream: true`: stops the stream, resumes SABnzbd, closes StreamPilot - the original behaviour). POST `/quit` reads `end_stream` from the JSON body (defaults `true` if absent/malformed); `Daemon.stop(end_stream=...)` decides whether `start()`'s shutdown path calls `_on_no_game()`.

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
    "base_tags": ["English", "Australia"],
    "channel_name": "davo1776"
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
      "tags": ["DeadByDaylight", "Horror"],
      "emoji": "🔪"
    }
  }
}
```

`obs_window` format: `Window Title:Window Class:Executable` - generated by `add-game` wizard.

**Dynamic title and tags** (both optional, applied in the same PATCH that sets the category - no extra API calls):
- `twitch.title_template` - format string with `{game}` placeholder, applied when a game has no per-game `title`. Defaults to `Davo plays {game}!`. Truncated to Twitch's 140-char limit.
- `twitch.base_tags` - list of tags always applied, combined with each game's `tags`.
- Per game: `title` - overrides the template entirely for that game. `tags` - added on top of `base_tags`. `emoji` - optional, appended as `" <emoji>"` to the end of the built title (`stream_meta.py::build_title`), e.g. `🐰` for Palworld, `⚡` for Marvel Rivals, `🔪` for Dead by Daylight. Dropped (not truncating the base title) if adding it would exceed the 140-char limit - a half-cut emoji or a chopped word reads worse than no emoji at all.
- Tags are sanitized to Twitch's rules: alphanumeric only, max 25 chars each, max 10 tags total, case-insensitive dedupe.

**`twitch.channel_name`** (optional, e.g. `"davo1776"`) - renders a "Watch on Twitch ↗"
link on the dashboard (`https://www.twitch.tv/{channel_name}`) so David can jump straight
to the live view. Passed from `config.py` -> `streampilot.py::cmd_start` ->
`dashboard_server.run(twitch_channel=...)`, substituted into `INDEX_HTML`'s
`__TWITCH_LINK_HTML__` placeholder by `index_html_bytes()` per request (not baked in at
import time, since it's config-driven, unlike everything else in `INDEX_HTML`). Omitted
entirely (no link rendered) if not configured.

## CLI Commands

Users run `scripts/run.bat` (and `scripts/setup/add-game.bat`) - these are thin wrappers that call the Python CLI below. The table is for Claude's reference, not user instructions.

| Command | Invoked by |
|---|---|
| `pythonw src/streampilot.py start --dashboard --watch` (daemon + dashboard + hot-reload, one process, no console) | `scripts/run.bat` (the desktop shortcut target) - hot-reload is on by DEFAULT (2026-07-19) |
| `python src/streampilot.py dashboard` (reopen the dashboard tab without restarting the daemon) | manual CLI only, no `.bat` - rarely needed |
| `python src/streampilot.py config add-game` | `scripts/setup/add-game.bat` |
| `python src/streampilot.py start --dashboard` (no `--watch`) | manual CLI only - only if you deliberately want hot-reload OFF |

## Always specify encoding='utf-8' on file I/O (rule, added 2026-07-21)

**Every `open()` call touching `config.json`, `status.json`, or any file that
could ever hold non-ASCII text (emoji, names, etc.) must pass
`encoding='utf-8'` explicitly.** Windows' default text encoding is the
system codepage (cp1252 here), not UTF-8. Without the explicit arg, reading
a file containing literal UTF-8 multi-byte sequences (not `\uXXXX`-escaped)
raises `UnicodeDecodeError`. **Incident (2026-07-21):** adding a per-game
`emoji` field to `config.json` crashed the live daemon on the very next
hot-reload - `config.py::load()`'s `open(path, 'r')` had no encoding, so
`json.load()` blew up on the emoji bytes. Invisible under `pythonw` (stderr
to devnull) - the process just silently died, same failure shape as the
2026-07-19 psutil incident below. Fixed in `config.py` and `status_file.py`;
regression test in `tests/test_config.py::test_load_handles_non_ascii_unicode_in_config`.
`hot_reload.py` already did this correctly (`open(path, "r", encoding="utf-8")`)
- match that pattern in any new file I/O.

## Never kill a live running instance (rule)

**If StreamPilot is running while Claude is editing this repo (real stream may be
live), NEVER kill/stop the process to "apply changes" or to test something** -
that stops the actual OBS stream and ends the VOD mid-session. Before running
`run.bat`, `python src/streampilot.py start`, or any command that would start a
second instance, or before using `taskkill`/`Stop-Process` on `pythonw`/`python`
for this repo: check first (`Get-Process pythonw -ErrorAction SilentlyContinue`,
or tail the newest `data/logs/*.log`, or `curl http://localhost:8765/status.json`).
If it's already running: **use the hot-reload trigger instead** - touch/create
`data/state/reload.trigger` once the edit is fully wired up (see hot-reload
section below). This restarts the process in place (adopts the existing session
via `_reconcile_existing_session()`) without ending the stream. Ask David before
doing anything that would stop the stream (killing the process, `run.bat`
double-launch, etc.) if hot-reload genuinely can't apply the change (e.g. a
change to `run.bat` itself, which isn't watched).

## Dev mode: hot-reload (`--watch`) - on by default via `run.bat`

**On by default, not opt-in** - `run.bat` (and therefore the desktop shortcut) always
passes `--watch`, so David can edit source while actively streaming and see the change
land within ~1-2s, without a separate dev-mode launch step. `scripts/setup/make-desktop-shortcut.ps1`
regenerates the Desktop shortcut (removes any existing `StreamPilot*.lnk` first, then
creates one clean one pointing at `run.bat`) - re-run it any time the shortcut goes
missing or gets manually duplicated; verify with `tests/test-desktop-shortcut.ps1`.
The shortcut itself carries no launch args - `run.bat` is the single source of truth,
so changing hot-reload behaviour means editing `run.bat`, not the shortcut.
`src/hot_reload.py` polls every `.py` file under `src/` (plus `config.json` via
`extra_files=` - not a `.py` file and not under `src/`, but still worth reacting to)
once a second (`snapshot()`/`watch_loop()`, stdlib only).

**Two ways a restart triggers - use the explicit one when building a feature:**
- **Explicit "reload now" signal (preferred):** touch/create
  `data/state/reload.trigger` (any content, even empty) - the very next poll consumes
  it (deletes the file) and restarts immediately, no waiting. This is the mechanism
  for a deliberate multi-file/multi-minute feature build: keep editing across several
  files for as long as needed (a long pause mid-build never auto-restarts anything),
  then touch the trigger once everything is actually wired up and ready.
  From Claude's Bash tool: `touch "C:/Users/David/GitHubRepos/StreamPilot/data/state/reload.trigger"`
  (create the file if the `touch` command isn't available - content doesn't matter, only
  its existence).
- **Passive fallback (very long debounce, 1 hour default - `DEBOUNCE_SECONDS`):** if
  nobody signals, the watcher eventually restarts on its own once the file set has gone
  quiet for that long - purely a "someone forgot to touch the trigger" backstop, not a
  mechanism a real feature build should ever race against. Deliberately this long: even
  a 30s debounce is still short enough to interrupt a genuine multi-minute build, which
  is the exact failure this two-path design avoids (raised by David 2026-07-19, twice -
  first the 2s-only version, then again when 30s turned out to still be too short).

Either path is gated by a **syntax check** (`check_syntax()`, in-memory `compile()`, no
bytecode-cache side effect) before actually restarting - if anything doesn't parse, the
watcher logs a warning and keeps the old (working) process running, re-checking every
poll, instead of restarting into a guaranteed crash. This does NOT catch a semantic/
runtime bug (that's what the psutil-race incident above was) - see
`feedback_live_process_hotreload_verify_liveness.md` for the verification discipline
that covers the rest. Once ready, it calls `os.execv(sys.executable, sys.argv)` to
restart the whole process in place with the same args - this reloads **all** code, not
just the dashboard HTML, since Python doesn't hot-reload imported modules on its own.
Restarting the StreamPilot process does NOT stop the actual OBS stream (OBS is a
separate process, only reconnects over WebSocket) - safe to use while a real stream is
live.
The already-open dashboard browser tab then reloads **itself**: `Daemon.build_id`
(a timestamp set once per process start) rides along on every `status.json`
heartbeat; the dashboard's `tick()` JS remembers the first `build_id` it sees and
calls `location.reload()` the moment a later poll shows a different one - so a code
change shows up in the open tab within about a second of the restart, no manual F5.
This is the concrete case the "dashboard live-reload" idea in `docs/IDEAS.md`
proposed generalizing further (serving HTML from disk, etc.) - the `--watch` +
`build_id` mechanism above is the version actually shipped (2026-07-19).

**Restart doesn't re-open a new browser tab.** `os.execv` re-runs `cmd_start` from
scratch, which used to unconditionally pass `open_browser=True` - every hot-reload
restart popped a fresh tab. `hot_reload.py` now sets `STREAMPILOT_HOT_RELOAD_RESTART=1`
on `os.environ` right before `execv` (inherited by the re-exec'd process automatically);
`cmd_start` checks it and only opens a tab on the true first launch.

**Restart adopts an already-live session instead of restarting the stream.** A fresh
`Daemon` always starts with `_active_game_exe=None`; without `_reconcile_existing_session()`
(called once in `start()` before the loop), every restart while a game was already
running would look like a brand-new launch and call `_on_game_launch()` - stopping the
live stream ("Ending previous VOD") and immediately restarting it, splitting the VOD and
briefly erroring (OBS rejects `StartStream` mid-teardown) for no reason. The reconcile
check adopts the existing session (`_detect_game()` + `obs.is_streaming()`) when a known
game is already live, so the heartbeat resumes monitoring without touching OBS.
**Also re-PATCHes title/tags to Twitch** (no `game_id` - category is untouched, stream
not restarted) so a code-only change to title-building logic takes effect on the live
title immediately, not just on the dashboard, without waiting for the next game launch
(added 2026-07-21, see HISTORY.md).

**Incident (2026-07-19): the daemon crashed and stayed down** while iterating with
`--watch` live. Root cause: `_detect_game()` called `p.name()` live on each process in
`psutil.process_iter(['name'])` - a process can exit between being listed and that call,
raising `psutil.NoSuchProcess` uncaught. Under `pythonw.exe` (headless, stdout/stderr
redirected to devnull per this file's CLI-entry-point guard) the traceback was invisible
and the process just vanished, taking the dashboard down with it (`Get-Process pythonw`
showed nothing running). Fixed by reading psutil's pre-fetched `p.info['name']` (from the
`attrs=['name']` already requested) instead of live-querying `.name()` - psutil silently
drops any process whose attrs failed to populate, so this has no race. General lesson
captured workspace-wide: `ClaudeOnly/memory/feedback/feedback_live_process_hotreload_verify_liveness.md`
- a green pytest run does not prove a live `--watch`-driven process survived an edit;
verify liveness (`curl http://localhost:8765/status.json`, `Get-Process pythonw`, or tail
the newest `data/logs/*.log`) after each risky edit, not just at the end.

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
│   ├── hot_reload.py        # --watch file-watcher + self-restart (os.execv)
│   ├── window_safety.py     # Blacklist: never stream a browser/desktop/terminal
│   └── config.py            # Loader + validator
├── assets/
│   ├── StreamPilotIconICO.ico    # Program icon (desktop shortcut, tray)
│   └── StreamPilotIconPNG.png
├── config/
│   ├── config.example.json
│   └── config.json          # gitignored
├── docs/
│   ├── IDEAS.md
│   └── HISTORY.md
├── scripts/
│   ├── run.bat              # desktop shortcut target - launches with --watch by default
│   ├── run-tests.bat
│   └── setup/
│       ├── add-game.bat
│       ├── install-dependencies.bat
│       └── make-desktop-shortcut.ps1  # (re)creates the Desktop shortcut, cleans duplicates
├── tests/                   # pytest suite + test-desktop-shortcut.ps1 (shortcut verification)
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
