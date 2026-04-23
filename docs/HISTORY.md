# History

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
