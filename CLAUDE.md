# StreamPilot - Claude Context

Python CLI daemon that auto-manages OBS streaming + SABnzbd when launching a known game. This file is orientation, safety rules and commands only. Implementation detail (architecture, config reference, hot-reload, incident history, repo layout) is in `docs/References/DevContext.md`; read its relevant section before touching `daemon.py`, `dashboard_server.py` or `hot_reload.py`. User docs: `README.md`, `docs/SETUP.md`.

## Key Paths

- OBS executable: `C:\Program Files\obs-studio\bin\64bit\obs64.exe`
- Dashboard visual consistency rules (palette, typography, buttons, toggles): `docs/DESIGN.md` - read before editing `dashboard_server.py`'s `INDEX_HTML`.
- Implementation detail and history: `docs/References/DevContext.md`. Setup steps: `docs/SETUP.md`. Status contract: `docs/References/state-contract.md`.

## Safety: never stream a non-game window (rule, added 2026-07-19)

**Twitch is completely public. StreamPilot must never let OBS's Game Capture window resolve to a browser, the raw desktop, or a terminal/editor** - any of those could leak private tabs, files, or credentials to the whole audience. Enforced in three places (`src/window_safety.py` is the single shared blacklist all three read from - extend the list there, never duplicate it):
1. **Config validation** (`config.py::_validate`) - daemon refuses to start if any `games` entry's exe key or `obs_window` resolves to a blacklisted exe.
2. **add-game wizard** (`streampilot.py::cmd_add_game`) - refuses to save a blacklisted window, before it ever reaches config.json.
3. **Live heartbeat check** (`daemon.py::_print_heartbeat`, the important one) - reads OBS's ACTUAL current Game Capture window every cycle and force-stops the stream immediately if it's ever blacklisted, regardless of how it got there (config edited by hand, OBS meddled with directly, a future bug elsewhere). The normal window-mismatch correction then reapplies the expected (safe) game window in the same cycle; the stream-restart-if-stopped correction is skipped for that cycle so it doesn't immediately undo the force-stop.
Default blacklist: common browsers (chrome/edge/firefox/brave/opera/iexplore), raw desktop (explorer.exe, dwm.exe), terminals/editors (cmd/powershell/pwsh/WindowsTerminal/ notepad/Code), and OBS itself (obs64/obs32 - capturing OBS's own window is a meaningless mirror loop).

## Safety: audio privacy guard (rule, added 2026-07-28)

**A leaked private audio source (Discord, a second monitor's game audio, a browser tab) is invisible and unrecoverable once streamed.** The audio side uses an allow-list (only known-safe exes may be present in the OBS "Application Audio Output Capture" source), the inverse of the video guard's blacklist. It is enforced by `src/audio_safety.py`, config validation, a preflight before every `start_stream()`, a live heartbeat check that force-stops the stream on any violation, auto-add of the active game, a Desktop Audio / Mic mute check and exclusive-mode convergence of the capture list. Full enforcement detail (all 7 points) is in `docs/References/DevContext.md`, "Audio privacy guard: full enforcement detail". Surfaced on the dashboard per the rule below.

## Dashboard is the source of truth (rule)

**Whenever a new feature sets or changes a Twitch/OBS setting (title, tags, category, anything else), it MUST be surfaced on the browser dashboard in the same change.** The dashboard exists so David never has to open Twitch or OBS to confirm something is set correctly - it's the single centralised view. Concretely: add the value to the daemon's dashboard-facing state (`self._current_*` in `daemon.py`, cleared in `_on_no_game`), include it in the `status_file.write_status(...)` call in `_print_heartbeat`, and add a row to `INDEX_HTML` in `dashboard_server.py` (both the static row markup and the JS `tick()` function that fills it in). Applied for Title and Tags (2026-07-18) - see `_current_title`/`_current_tags` in `daemon.py` and the Title/Tags rows in `dashboard_server.py`. Applied for the audio privacy guard (2026-07-28) - see the Audio row in `dashboard_server.py` and the safety rule above.

## Never kill a live running instance (rule)

**If StreamPilot is running while Claude is editing this repo (real stream may be live), NEVER kill/stop the process to "apply changes" or to test something** - that stops the actual OBS stream and ends the VOD mid-session. Before running `run.bat`, `python src/streampilot.py start`, or any command that would start a second instance, or before using `taskkill`/`Stop-Process` on `pythonw`/`python` for this repo: check first (`Get-Process pythonw -ErrorAction SilentlyContinue`, or tail the newest `data/logs/*.log`, or `curl http://localhost:8765/status.json`). If it's already running: **use the hot-reload trigger instead** - touch/create `data/state/reload.trigger` once the edit is fully wired up (see hot-reload section below). This restarts the process in place (adopts the existing session via `_reconcile_existing_session()`) without ending the stream. Ask David before doing anything that would stop the stream (killing the process, `run.bat` double-launch, etc.) if hot-reload genuinely can't apply the change (e.g. a change to `run.bat` itself, which isn't watched).

## Always specify encoding='utf-8' on file I/O (rule, added 2026-07-21)

**Every `open()` call touching `config.json`, `status.json`, or any file that could ever hold non-ASCII text (emoji, names, etc.) must pass `encoding='utf-8'` explicitly.** Windows' default text encoding is cp1252, not UTF-8. Incident and regression test: DevContext.md, "utf-8 incident".

## Status/state field design (rule, added 2026-07-25)

**A status field shown on the dashboard must only ever encode current physical truth, never a transient "an action was just taken" event.** Put correction events in the log line, not the polled state field. Incident and detail: DevContext.md, "Status/state field design: detail".

## CLI Commands

Users run `scripts/run.bat` (and `scripts/setup/add-game.bat`) - these are thin wrappers that call the Python CLI below. The table is for Claude's reference, not user instructions.

| Command | Invoked by |
|---|---|
| `pythonw src/streampilot.py start --dashboard --watch` (daemon + dashboard + hot-reload, one process, no console) | `scripts/run.bat` (the desktop shortcut target) - hot-reload is on by DEFAULT (2026-07-19) |
| `python src/streampilot.py launch [--port N] [--no-browser] [--no-watch]` (replace by port owner, start detached windowless, return when it answers) | `scripts/run.bat` after `preflight` and self-elevation |
| `python src/streampilot.py preflight` (python, imports, config, port; prints each problem, exit 1) / `check` (URL, pid, boot id, sha, status; exit 0 running, 1 not running, 2 port held by another program) / `stop` (dashboard process only: POST /quit with end_stream false, then kill the port owner; never ends the stream) | Claude, scripts, `run.bat` |
| `python src/verify.py` (tests + fixture capture, one VERIFY PASS/FAIL line) / `python src/streampilot.py fixture` (a scenario on a spare port) | Claude, after any change; never touches the live server |
| `python src/streampilot.py dashboard` (reopen the dashboard tab without restarting the daemon) | manual CLI only, no `.bat` - rarely needed |
| `python src/streampilot.py config add-game` | `scripts/setup/add-game.bat` |
| `python src/streampilot.py start --dashboard` (no `--watch`) | manual CLI only - only if you deliberately want hot-reload OFF |

## Webapp standard

This dashboard follows a shared webapp standard (checklist of WS ids); backlog items cite WS ids.
