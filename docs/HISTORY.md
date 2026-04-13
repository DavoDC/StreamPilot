# History

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
