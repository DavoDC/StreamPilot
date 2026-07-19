# History

---

## 2026-07-19 - hot_reload.py: explicit "reload now" trigger, replaces fixed 2s debounce

David's concern with the previous fix: a real feature build is a series of edits over
several minutes with pauses well over the old 2s debounce window (reading a file,
thinking, running tests) - a short passive debounce risks auto-restarting mid-build into
syntax-valid-but-half-wired code. Fix: a deliberate signal, not a timer.

- **`data/state/reload.trigger`** - touch/create this file (any content) and the very
  next poll consumes it and restarts immediately, after the existing syntax check. No
  sockets/ports - simplest possible local IPC, same "simple state file" convention as
  `status.json` right beside it (gitignored the same way).
- **`DEBOUNCE_SECONDS` bumped 2 -> 30** - now purely a lazy passive fallback for a quick
  one-line edit nobody explicitly signals, not the primary mechanism.
- Both paths still gated by the syntax check from the previous fix.

Going forward: build a feature across as many edits/files as needed (no auto-restart
risk mid-build), then touch the trigger file once it's actually ready.

**Same day, follow-up:** 30s still wasn't long enough - a 3-minute feature build could
still race it. Since the trigger is the intended primary mechanism (confirmed working
live: touched the file, restarted within ~2s per the log line "Reload triggered
explicitly..."), the passive fallback isn't something a real build should ever be
racing at all. Bumped `DEBOUNCE_SECONDS` 30 -> 3600 (1 hour) - purely a "forgot to
signal" backstop now.

## 2026-07-19 - hot_reload.py: watch config.json, debounce, syntax gate

Prompted by two things David raised after the previous fixes landed: (1) the
"Watch on Twitch" feature needed a source-file touch to pick up because
config.json isn't watched by `--watch` (only `.py` files were), and (2) a
general concern that restarting on every single save risks hot-reloading a
half-written feature mid-edit.

- `extra_files=` param on `snapshot()`/`watch_loop()`/`start_watcher()` -
  `streampilot.py` passes `[config.CONFIG_PATH]` so a config edit now
  triggers a restart same as a code edit, no more manual touch needed.
- **Debounce** (2s default) - a burst of several saves building one feature
  now collapses into a single restart once the file set goes quiet, instead
  of restarting after every individual save.
- **Syntax gate** (`check_syntax()`) - before restarting, every changed `.py`
  file must actually compile (in-memory `compile()`, no bytecode-cache file
  written). A syntax error just means "not ready yet" - the watcher logs a
  warning and keeps the old working process running, re-checking each poll,
  rather than restarting into a guaranteed crash.

Neither catches a semantic/runtime bug (only a genuine syntax error) - the
psutil-race crash earlier this session would NOT have been caught by this,
that's what the liveness-verification discipline
(`feedback_live_process_hotreload_verify_liveness.md`) is for.

## 2026-07-19 - "Watch on Twitch" dashboard link

New `twitch.channel_name` config key (set to `davo1776`) renders a small "Watch on
Twitch ↗" link on the dashboard so David can jump straight to the live view without
typing the URL. Unlike Title/Tags (which change per game and flow through the daemon's
heartbeat/status.json), the channel name is a constant per user, so it's rendered
directly into `INDEX_HTML` via a template placeholder (`index_html_bytes()`) at request
time instead of round-tripping through the daemon - simpler, no extra moving parts.
Omitted entirely if not configured.

Note while shipping this: config.json isn't watched by hot-reload (`--watch` only
watches `.py` files), so a config-only change needs a `.py` file touched (or the daemon
restarted normally) to take effect - not a bug, just a reminder for next time a
config-driven dashboard feature is added.

## 2026-07-19 - Live-tested hot-reload against David's real stream: 3 bugs found and fixed

David ran `--watch` live while actually streaming Palworld and had Claude exercise it
end-to-end (test UI/code changes, browser auto-reload verification via MCP). Surfaced
three real bugs that unit tests alone hadn't caught:

1. **New browser tab on every restart** - `os.execv` re-runs `cmd_start`, which always
   passed `open_browser=True`. Fixed: `hot_reload.py` sets an env var before `execv`;
   `cmd_start` checks it and only opens a tab on the true first launch.
2. **Stream stopped/restarted on every hot-reload (VOD-splitting bug)** - a fresh
   `Daemon` forgets `_active_game_exe`, so a restart while a game was already running
   looked like a fresh launch and ran the full stop+restart flow, briefly erroring
   ("Ending previous VOD" -> OBS rejects `StartStream` mid-teardown -> heartbeat
   flips to ISSUE -> self-heals). This is what David saw as "OK briefly said ISSUE".
   Fixed: `_reconcile_existing_session()` adopts an already-live session instead.
3. **The daemon actually crashed and stayed down** - `_detect_game()`'s live `p.name()`
   call raced against `psutil.NoSuchProcess` (a process can exit between listing and
   the call). Under `pythonw.exe` the traceback was swallowed silently and the process
   just died, taking the dashboard with it - unnoticed for several minutes. Fixed by
   reading psutil's pre-fetched `p.info['name']` instead of live-querying `.name()`.

General lesson (workspace-wide, not StreamPilot-specific): a green pytest run does not
prove a live `--watch`-driven process survived an edit, since mocks can't reproduce real
external-library races. Captured in
`ClaudeOnly/memory/feedback/feedback_live_process_hotreload_verify_liveness.md` and
`.claude/rules/enforced-rules.md`.

Also added: window-capture safety blacklist (`src/window_safety.py`) - config
validation, add-game wizard, and a live heartbeat check all refuse to ever stream a
browser/desktop/terminal window, since Twitch is public. See CLAUDE.md's safety section.

---

## 2026-07-19 - Hot-reload on by default via run.bat + desktop shortcut maker

Flipped `--watch` from opt-in to the default: `run.bat` (the desktop shortcut
target) now always launches `streampilot.py start --dashboard --watch`, so
David can edit source and see the change land in the running program within
~1-2s while actively streaming, with no separate dev-mode launch step.

Added `scripts/setup/make-desktop-shortcut.ps1` (+ `tests/test-desktop-shortcut.ps1`),
matching the Claude Code shortcut-maker pattern already used in the workspace
repo - removes any existing `StreamPilot*.lnk` on the Desktop first (two stale
duplicates, "StreamPilot.lnk" and "StreamPilot (2).lnk", were cleaned up as
part of shipping this), then creates exactly one shortcut pointing at
`run.bat`. The shortcut carries no launch args itself - `run.bat` is the
single source of truth, so this script never needs updating again just
because the launch command changes. Verified: 8/8 checks pass.

Desktop-shortcut polish ideas (`.bat` double-click wrapper, add-game wizard
offering to run this at first-time setup, etc.) captured in IDEAS.md, not
implemented.

## 2026-07-19 - Hot-reload dev mode + 3-option Quit dialog

**Hot-reload (`--watch`):** new opt-in CLI flag (`start --watch`, superseded
same day by the default-on flip above) starts `src/hot_reload.py`'s file-watcher - polls every `.py` file
under `src/` once a second, and the moment any changes, restarts the whole
process in place via `os.execv` (picks up ANY code change, not just HTML/CSS,
since Python doesn't hot-reload imported modules on its own). Restarting the
process does not stop OBS's actual stream (separate process, only reconnects
over WebSocket) - safe mid-stream. `Daemon.build_id` (set once per process
start) rides along on every `status.json` heartbeat; the dashboard's `tick()`
JS remembers the first value it sees and calls `location.reload()` once a
later poll shows a different one, so an already-open dashboard tab reloads
itself within about a second of a restart - no manual F5. Supersedes the
"Live-reload the dashboard" idea that was in IDEAS.md.

**3-option Quit dialog:** the single "Quit" confirm from 2026-07-17 (below)
is now Cancel / "Keep streaming" / "End stream". "Keep streaming" closes only
the StreamPilot process - OBS keeps streaming, SABnzbd stays paused (resuming
it while the stream continues would tank bandwidth, defeating the whole point
of the pause). "End stream" is the original behaviour (stop stream, resume
SABnzbd, close). `POST /quit` now reads `end_stream` (bool) from a JSON body,
default `true`; `Daemon.stop(end_stream=...)` decides whether `start()`'s
shutdown path calls `_on_no_game()`.

---

## 2026-07-17 - Dashboard Quit button (clean shutdown from the browser)

Since `run.bat` launches headless via `pythonw.exe`, there was no window to
close and no console to Ctrl+C - Task Manager was the only way to stop
StreamPilot. Added a Quit control to the dashboard itself instead of building
the system tray early (tray's shutdown-control rationale is now covered here;
see IDEAS.md tray section).

- **`dashboard_server.py`** gained a `POST /quit` route and an `on_quit`
  callback param on `run()`. The dashboard's existing "reassurance" design
  language (dark panel, muted default state) carried over to the new
  control: a small, unobtrusive "Quit" button below the status panel opens a
  confirmation dialog (not a native `confirm()` popup) explaining exactly
  what will happen - "This stops the stream, resumes SABnzbd, and closes
  StreamPilot" - with Cancel as the calm default and Quit visually distinct
  (red) as the deliberate action. Prevents an accidental click from killing
  a live stream.
- **`daemon.py`** needed no changes - `stop()` already existed, and
  `_on_no_game()` (already run in `start()`'s `finally` block) already does
  exactly the stop-stream/resume-SAB sequence the quit flow needs.
- **`streampilot.py`**'s `cmd_start` now passes `daemon.stop` as the dashboard
  thread's `on_quit` callback, and calls `os._exit(0)` after `daemon.start()`
  returns - nothing previously called `daemon.stop()` in practice, so nothing
  guaranteed the headless process actually terminated once the polling loop
  stopped.
- Verified live: ran an isolated test server on a separate port (never
  touching the port the real running daemon was already bound to, since
  David was streaming at the time) and drove the button through Chrome -
  Cancel closes cleanly, Quit disables the buttons, updates the copy to
  "Stopping the stream and closing StreamPilot...", and fires the POST.

---

## 2026-07-14 - Silent launch (no terminal), stale-instance kill, status.json moved

David wanted the desktop shortcut to launch with zero visible console window and to
never stack up duplicate running instances across repeat clicks or dev restarts.

- **`run.bat`** now self-elevates first (still one UAC prompt - required for OBS game
  capture), then, while elevated, kills any previously running `streampilot.py`
  process (matched by command line via `Get-CimInstance`/`Stop-Process`), then
  launches via `pythonw.exe` instead of `python.exe` - `pythonw` has no console at
  all, so nothing flashes on screen. Tried a two-file VBScript wrapper approach
  first (`run-silent.vbs` + `run-hidden.vbs`) to sidestep cmd.exe's console-on-launch
  behavior, but David wanted to stay at one script file, so it collapsed back into
  `run.bat` alone using `Start-Process -Verb RunAs -WindowStyle Hidden`.
- **Ordering bug caught during testing:** the kill step must run AFTER elevation -
  a non-admin process gets `Access is denied` (blank `CommandLine`, can't even see
  it to match) against an already-elevated instance, so killing before elevating
  silently no-ops on exactly the processes it's meant to catch.
- **`sys.stdout`/`sys.stderr` are `None` under `pythonw.exe`** (confirmed by direct
  test, not assumed) - any `print()` or the existing `logging.StreamHandler(sys.stdout)`
  would crash. `streampilot.py` now patches both to a devnull sink at import time if
  they're `None`; file logging in `data/logs/` is unaffected either way.
- **Dashboard URL** changed from `http://127.0.0.1:8765/` to `http://localhost:8765/`
  (cosmetic, same server).
- **`data/logs/status.json` moved to `data/state/status.json`** - it's live
  daemon<->dashboard heartbeat state overwritten every poll, not a timestamped
  historical log, so it didn't belong mixed in with `streampilot_*.log` files.
  Matches the workspace's `data/state/` vs `data/logs/` convention.

---

## 2026-07-13 - Consolidated to one launcher: run.bat now starts daemon + dashboard

The `start-all.bat` added earlier today was immediately redundant - David's
desktop shortcut (checked live: `TARGET: scripts\run.bat`, no args) already
points at `run.bat`, so a THIRD script wasn't the one-click answer; making
`run.bat` itself do both was. Simplified:

- **`run.bat`** now calls `streampilot.py start --dashboard` (both the direct
  and admin-elevated paths) instead of plain `start`. The existing desktop
  shortcut needed zero changes - it already targets `run.bat` with no
  arguments, so this was a pure behind-the-shortcut upgrade.
- **Deleted `scripts/dashboard.bat` and `scripts/start-all.bat`** - both
  redundant now that `run.bat` covers the combined case. The
  `streampilot.py dashboard` CLI subcommand itself stays (useful to reopen the
  tab without restarting the daemon) but has no dedicated `.bat` anymore.
- Docs (CLAUDE.md, README.md, IDEAS.md) updated to match; this HISTORY.md
  keeps the earlier same-day entries as-written rather than rewriting them,
  per the "history is a log, not a whiteboard" norm - this entry documents the
  correction on top.
- Full test suite green (no test changes needed - the deleted files had no
  code, just launcher wrappers around already-tested CLI wiring).

---

## 2026-07-13 - Tab title/favicon state + one-click combined launcher

David wanted to monitor stream state by glancing at the browser tab (title/icon)
without needing it focused, and a single launcher that starts the daemon and
opens the dashboard together instead of two separate clicks.

- **Tab title now shows a colored dot + game name** (🟢 OK / 🔴 ISSUE / ⚪ IDLE /
  ⚫ OFFLINE, e.g. "🟢 Marvel Rivals - StreamPilot"), updated every poll tick.
- **Favicon recolors to match state** - a small inline SVG (data URI, no image
  asset needed) built client-side and swapped via the `<link rel="icon">` href.
- Harder follow-ups (genuinely animated/blinking favicon, browser notification
  on OK->ISSUE, audio ping) logged to IDEAS.md rather than built now - the
  static title/favicon recolor is the cheap, immediate win.
- **`streampilot.py start --dashboard`** runs the dashboard server in a
  background thread of the SAME process as the daemon - one command starts
  both, no second window/click needed. New **`scripts/start-all.bat`** mirrors
  `run.bat`'s admin auto-elevation (OBS needs it) and calls `start --dashboard`.
  `run.bat` and `dashboard.bat` are unchanged for anyone who wants them
  separately (e.g. dashboard tab already pinned open).
- Verified live: started the dashboard thread standalone (simulating the
  `--dashboard` code path without needing real OBS/Twitch credentials) and
  confirmed the server responds while "the daemon" runs, with the new
  title/favicon JS present in the served page.
- Full test suite green (2 new tests for the title/favicon markers).

---

## 2026-07-13 - Code review before setting up a new game: 2 real fixes

David asked for a foresight check before running `add-game.bat` for a new game.
Reviewed the add-game code path end-to-end (not just IDEAS.md) and found two
real issues, both fixed:

- **`twitch_client.py::search_game()` silently returned `[]` for both "no
  results" and any non-200 API response** (expired/revoked OAuth token, rate
  limit, Twitch outage) - only network exceptions were logged, an auth failure
  wasn't. In the wizard this looked identical to "your game isn't in Twitch's
  directory," with no way to tell the difference. Fixed: non-200 responses are
  now logged as a warning with the status code. Also added an explicit
  `twitch.validate()` check at the START of `cmd_add_game` (`streampilot.py`)
  that prints a clear terminal warning ("Twitch token appears invalid or
  expired...") instead of only surfacing the problem indirectly via a confusing
  "not found" message later. New regression test:
  `test_search_game_auth_error_logs_warning_not_silent`.
- **add-game's window picker only showed the first 20 of ALL visible top-level
  windows on the system**, unsorted/unfiltered, with no indication anything was
  cut off. On a realistic streaming desktop (game + OBS + Discord + browser +
  terminal) the target game could be pushed past the cutoff and simply never
  appear in the list. Raised the cap to 40 (`WINDOW_LIST_LIMIT`) and added an
  explicit "N windows open, only showing the first 40" note so a future
  truncation is visible instead of silent.
- Verified live: David's actual Twitch token was valid at review time (not the
  live risk today), but the silent-swallow was a real code gap regardless -
  future token expiry would have hit it. Current window count on his machine
  was well under both the old and new cap.
- Full test suite green (added 1 new test, all pre-existing tests untouched).

---

## 2026-07-13 - Live reassurance dashboard (local web page, second-screen browser tab)

David wanted the "glance at the terminal to confirm everything's OK" reassurance
loop replaced with a small sleek animated status view, cheapest and simplest
possible. First cut was a tkinter window; David then asked for a browser-based
version instead, so it was rebuilt as a local web page (tkinter removed same day).

- **`src/status_file.py`** - the daemon<->dashboard JSON contract. `write_status()`
  (atomic: write to `.tmp` then `os.replace`), `read_status()` (returns `None` on
  missing/corrupt file), `is_stale()` (daemon presumed dead if no write within
  `poll_interval * 4`, floor 8s). Covered by unit tests, all pure functions.
- **`daemon.py` refactor** - extracted `_classify()` from `_format_heartbeat` so
  the terminal log line and the new JSON write share one source of truth instead
  of duplicating the OK/ISSUE/game/category/SABnzbd logic. `_format_heartbeat`
  keeps its original signature/behaviour (pre-existing tests untouched,
  unmodified, still passing). Every heartbeat now also writes
  `data/logs/status.json` (gitignored).
- **`src/dashboard_server.py`** - a tiny local web server, Python stdlib
  `http.server` only, zero new dependencies (no Flask/FastAPI, no Node, no
  build step - deliberately NOT AudioManager's NiceGUI stack, which is overkill
  for one status page). Serves a single-file HTML/CSS/JS page that polls
  `/status.json` every second and opens automatically in the default browser.
  **Security-by-construction:** the handler serves exactly two routes (`/` and
  `/status.json`) instead of the directory tree, so `config.json`'s secrets
  (OAuth token, OBS password, SABnzbd API key) can never be reached through it
  - verified live with a direct guess AND a `/../config/config.json` path-
  traversal attempt, both correctly 404. Shows a big colored OK (green) / ISSUE
  (red) / IDLE (grey) / OFFLINE badge, a continuously pulsing heartbeat dot (CSS
  animation - proves the page itself is alive, independent of daemon state), and
  Game/Category/SABnzbd rows with a "last updated Xs ago" footer.
- Wired as `streampilot.py dashboard` (CLI subcommand) + `scripts/dashboard.bat`
  (thin launcher, no admin elevation needed - only `run.bat` needs that for OBS).
- **Verified live**, not just unit-tested: started the real server, fetched `/`
  and `/status.json` over HTTP and confirmed correct content, then confirmed the
  security property above with real requests.
- Full test suite green.

---

## 2026-04-25 - Quick fix: remove extra delay + redirect focus to AudioManager

- **Removed extra sleep from heartbeat polls** - `HEARTBEAT_EVERY` changed from 2 to 1. The `time.sleep(poll_interval)` now only fires in the `else` branch (non-heartbeat polls). Since every poll is now a heartbeat, the sleep never fires; Twitch/OBS/SABnzbd API calls (~3-5s combined) provide natural throttling. Result: status line interval drops from ~6-7s to ~3-5s.
- **IDEAS.md redirected to AudioManager** - added a stop banner at the top of IDEAS.md: StreamPilot is feature-complete for current use; new work goes to AudioManager.
- Test updated: `test_loop_fires_heartbeat_every_2nd_poll` renamed and rewritten to assert heartbeat fires every poll and sleep is never called.
- 69 tests, all passing.

---

## 2026-04-25 - P1 QOL batch: logging overhaul + Steam auto-relaunch

- **Timestamped log files per run** - log files are now `data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log` (one per run, never appended). Was: single `streampilot.log` overwritten each run.
- **Uniform timestamp prefix** - all log lines now use `[YYYY-MM-DD HH:MM:SS] [LEVEL] name: message`. Both FileHandler and StreamHandler share the same formatter so terminal output and log file are 1:1.
- **All print() removed from daemon** - every event (game launch, stream start/stop, SABnzbd pause/resume, OBS launch, heartbeat) now routes through `log.info()`. Eliminated the split where some events appeared on screen but not in the log file.
- **run-tests.bat now produces a log** - added `--log-file=data\logs\run-tests.log` to pytest invocation.
- **Auto-relaunch Steam** - if Steam is not running when the daemon starts, it is launched automatically. Default path: `C:\Program Files (x86)\Steam\steam.exe` (matching the Start Menu shortcut); overridable via `steam.exe_path` in config. Same cwd-as-exe-dir pattern as OBS auto-launch.
- Fixed pre-existing test isolation bug: `SAMPLE_CFG` was a shared module-level dict; tests that mutated `daemon.cfg` were polluting subsequent tests. Fixed by `copy.deepcopy(SAMPLE_CFG)` in the fixture.
- 6 new tests added (5 Steam relaunch, 1 heartbeat no-embedded-timestamp). 69 total, all passing.

---

## 2026-04-24 - QOL batch: heartbeat cleanup + faster updates + obs_window fix

- **Removed OBS field from heartbeat** - `| OBS: Live` was redundant; OBS state is implied by `Status: OK/ISSUE`. Heartbeat now: `[HH:MM:SS] Status: OK | Streaming: X | Category: X | SABnzbd: X`. ISSUE still fires when OBS is offline.
- **Faster heartbeat** - `HEARTBEAT_EVERY` 5 -> 2 polls (~4s interval in practice; ~6-7s observed due to API call latency on heartbeat polls, vs ~10s before).
- **obs_window double-space fix** - added `.strip()` to window title in add-game wizard (`streampilot.py:103`) so future game captures don't produce trailing-space titles. Fixed `config.example.json`. Existing `config.json` entries unchanged (stream works; re-run add-game to regenerate clean strings if desired).
- 3 tests updated to match new behaviour. 63 total, all passing.

---

## 2026-04-24 - Game-per-VOD live test CONFIRMED

Verified game-per-VOD feature end-to-end in a live session. Feature confirmed working: launching a second game while streaming correctly stops the current stream and starts a fresh one (new VOD). Removed from IDEAS.md "Needs real-environment test".

---

## 2026-04-24 - SABnzbd resume on game/program stop CONFIRMED

David confirmed SABnzbd resume is already implemented and working: when StreamPilot detects the game has closed, or when StreamPilot itself exits, SABnzbd is automatically resumed. Removed from IDEAS.md Robustness section.

---

## 2026-04-24 - Delete status.bat + setup-config.bat; fix add-game.bat window close

- Deleted `scripts/status.bat` (redundant - startup checks cover it) and `scripts/setup/setup-config.bat` (single-purpose file copy; replaced with a manual copy instruction in README Step 3).
- Fixed `add-game.bat` closing immediately after the Python wizard exits: interactive wizard leaves buffered keypresses in stdin that instantly satisfy a trailing `pause`. Replaced final `pause` with `cmd /k` so the window stays open unconditionally.
- Updated CLAUDE.md repo structure and README Step 3 to match.

---

## 2026-04-24 - Add-game UX overhaul

Full rewrite of the `config add-game` wizard. Unblocks adding Dead by Daylight as a second game (now confirmed added and working).

Changes:
- **Arrow-key window selector** - replaced numbered list with `questionary.select`. Same pattern as RivalsVidMaker.
- **Auto-detect game name** - display name pre-fills from the selected window title; Twitch search runs automatically with that name. No manual Twitch lookup needed in the happy path.
- **Robust Twitch search** - new `search_game_robust()` method tries full name first, then first word only if empty. Fixes cases where the full game name returns no results.
- **Clarified display name prompt** - reworded from "Game name (for display)" to "Display name in StreamPilot dashboard" with inline default.
- **Removed duplicate prompt** - "Make sure your game is running" was shown twice (once by bat, once by Python). Python prompt removed; bat handles it.
- **Fixed end message** - was incorrectly saying `streampilot start`; now says `scripts\run.bat`.
- **Added `questionary>=2.0.0`** to `requirements.txt`.
- 4 new tests for `search_game_robust` (63 total, all passing).

---

## 2026-04-24 - Game-per-VOD (implemented, untested in live session)

Each game session is now its own VOD. When a new game is detected while a stream is already live, StreamPilot stops the current stream before starting a fresh one. Previously the stream stayed live across game changes (mid-session switch). This eliminates mid-session switch complexity and ensures every VOD is scoped to a single game session. 1 test updated, 59 total passing. Pending real-environment verification - see IDEAS.md.

---

## 2026-04-21 - Windows Terminal elevation

`run.bat` UAC relaunch now opens in Windows Terminal instead of a plain cmd window. Changed `Start-Process` target from the bat file itself to `wt.exe` with `cmd /k` and the python command inline. Elevated session opens as a proper WT tab.

---

## 2026-04-21 - Status heartbeat log (live dashboard)

Every 5th poll (~10s) prints a one-line status to the terminal so the second screen acts as a live dashboard while gaming.

Format: `[HH:MM:SS] Status: OK | Streaming: Marvel Rivals | OBS: Live | Category: Marvel Rivals | SABnzbd: Paused`

- `Status: OK/ISSUE` - top-level at-a-glance indicator. ISSUE fires if game is active and OBS is offline, SABnzbd is running, or SABnzbd is unreachable.
- OBS and SABnzbd state queried live from WebSocket/API each heartbeat - no caching.
- Twitch category queried live via new `TwitchClient.get_current_game_name()` (`GET /helix/channels`).
- Warning states surfaced inline: `OBS: OFFLINE - should be streaming`, `SABnzbd: RUNNING - should be paused`, `SABnzbd: Unreachable`.
- 9 new tests added (4 status tests, 5 heartbeat format/firing tests). Total: 40 -> 59 tests.

---

## 2026-04-20 - Twitch Category Fix (401 mismatch)

`set_game` was returning 401 "Client ID and OAuth token do not match". Root cause: tokens generated via twitchtokengenerator.com are ALWAYS bound to TTG's own Client ID (`gp762nuuqcoxypju8c569th9wz7q5`), regardless of what you enter in the optional "Use My Client ID" field. Even entering the correct Client ID from the Twitch Dev Console (`ejqn3v0vk0enothyenc1mryt2kywpm`) still produces a token paired with TTG's Client ID - confirmed by checking the CLIENT ID shown in TTG's generated tokens section.

Fix: set `twitch.client_id` in `config.json` to TTG's Client ID (`gp762nuuqcoxypju8c569th9wz7q5`). Confirmed working - Twitch category now sets correctly on game launch.

Note: TTG's optional "Use My Client ID" field appears non-functional for token binding. When using TTG, always use TTG's Client ID in config, not your own Twitch Dev app Client ID.

---

## 2026-04-20 - SABnzbd Pause Fix

SABnzbd pause was failing with WinError 10061 (connection refused) because the port in `config.json` was set to 8080 but SABnzbd was listening on a different port. Updated `config.json` with the correct port - SABnzbd now pauses correctly when streaming starts.

---

## 2026-04-20 - Launch OBS as Admin (P0 fix)

`run.bat` now auto-elevates via UAC before starting the daemon. When the daemon launches OBS via `subprocess.Popen`, OBS inherits admin rights from the elevated parent - required for Marvel Rivals game capture to work. Without elevation, game capture silently fails.

Added 4 unit tests for `_ensure_obs_running` (already-running, no exe_path, launches successfully, OBS timeout). Test count: 9 -> 13.

---

## 2026-04-19 - OBS Auto-Launch Fix

Fixed `daemon.py` `_ensure_obs_running()`: `subprocess.Popen` was called without `cwd`, defaulting to the script directory. OBS failed to find its plugins/DLLs. Fix: derive `cwd` from `os.path.dirname(os.path.abspath(exe_path))` so OBS launches with its own bin folder as working directory - matching Start Menu shortcut behaviour. Confirmed working in live test.

---

## 2026-04-13 - Test Suite (40 tests)

Added pytest test coverage for all five modules. Tests use `unittest.mock` to patch all external services (OBS WebSocket, Twitch API, SABnzbd, psutil process list) - no real connections needed to run them. `pytest.ini` sets `pythonpath = src` so imports resolve correctly.

Modules covered:
- `test_config.py` - 5 tests (validate passes, fails missing section/key, missing file exits, add_game writes)
- `test_obs_client.py` - 11 tests (connect success/failure/no-obsws, is_streaming, set_game_capture_window, start/stop/disconnect)
- `test_twitch_client.py` - 9 tests (oauth prefix strip, validate, set_game, search_game)
- `test_sabnzbd_client.py` - 6 tests (pause/resume, is_paused true/false/unreachable)
- `test_daemon.py` - 9 tests (detect_game, on_game_launch, on_no_game, sab disabled)

Added `scripts/run-tests.bat` for double-click test runs.

---

## 2026-04-13 - MVP Build

Built the full StreamPilot MVP in a single session. All five source modules implemented and working.

**Modules:**
- `config.py` - loads and validates `config/config.json`; `add_game()` writes new entries
- `obs_client.py` - OBS WebSocket v5 wrapper via `obsws-python`; connects, checks stream state, sets Game Capture window, starts/stops stream
- `twitch_client.py` - Twitch Helix API; validates OAuth token, sets channel category, searches games
- `sabnzbd_client.py` - SABnzbd JSON API; pause, resume, is_paused
- `daemon.py` - polling loop (2s default); detects game exes via `psutil`, triggers on-launch/on-exit actions
- `streampilot.py` - CLI entry point (`argparse`); subcommands: `start`, `status`, `config add-game`, `auth`

**Key details:**
- `config add-game` wizard uses `win32gui.EnumWindows` to detect running game windows and builds the OBS `window` string (`Title:WindowClass:Executable`) automatically
- `auth` command guides through twitchtokengenerator.com flow and saves token to config
- SABnzbd integration is optional (toggle via `sabnzbd.enabled` in config)
- `scripts/run.bat` for double-click launch
