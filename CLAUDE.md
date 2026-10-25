# StreamPilot - Claude Context

Python CLI daemon that auto-manages OBS streaming + SABnzbd when launching a known game. Orientation, safety rules and commands only; implementation detail, config reference, hot-reload and history are in `docs/References/DevContext.md` (read the relevant section before touching `daemon.py`, `dashboard_server.py` or `hot_reload.py`).

## Key Paths

- OBS executable: `C:\Program Files\obs-studio\bin\64bit\obs64.exe`
- Dashboard visual consistency rules (palette, typography, buttons, toggles): `docs/DESIGN.md` - read before editing `dashboard_server.py`'s `INDEX_HTML`.
- Setup steps: `docs/SETUP.md`. Status contract: `docs/References/state-contract.md`. Security review: `docs/References/SecurityReview.md`.

## Safety: never stream a non-game window (rule, added 2026-07-19)

**Twitch is completely public. StreamPilot must never let OBS's Game Capture window resolve to a browser, the raw desktop, or a terminal/editor** - any of those could leak private tabs, files, or credentials to the whole audience. Enforced in three places (`src/window_safety.py` is the single shared blacklist all three read from - extend the list there, never duplicate it):
1. **Config validation** (`config.py::_validate`) - daemon refuses to start if any `games` entry's exe key or `obs_window` resolves to a blacklisted exe.
2. **add-game wizard** (`streampilot.py::cmd_add_game`) - refuses to save a blacklisted window, before it ever reaches config.json.
3. **Live heartbeat check** (`daemon.py::_print_heartbeat`, the important one) - reads OBS's ACTUAL current Game Capture window every cycle and force-stops the stream immediately if it's ever blacklisted, regardless of how it got there (config edited by hand, OBS meddled with directly, a future bug elsewhere). The normal window-mismatch correction then reapplies the expected (safe) game window in the same cycle; the stream-restart-if-stopped correction is skipped for that cycle so it doesn't immediately undo the force-stop.
Default blacklist: common browsers (chrome/edge/firefox/brave/opera/iexplore), raw desktop (explorer.exe, dwm.exe), terminals/editors (cmd/powershell/pwsh/WindowsTerminal/ notepad/Code), and OBS itself (obs64/obs32 - capturing OBS's own window is a meaningless mirror loop).

## Safety: audio privacy guard (rule, added 2026-07-28)

**A leaked private audio source (Discord, a second monitor's game audio, a browser tab) is invisible and unrecoverable once streamed.** The audio side uses an allow-list (only known-safe exes may be present in the OBS "Application Audio Output Capture" source), the inverse of the video guard's blacklist. Enforcement (all 7 points) is in `docs/References/DevContext.md`, "Audio privacy guard: full enforcement detail". Surfaced on the dashboard per the rule below.

## Dashboard is the source of truth (rule)

**Whenever a new feature sets or changes a Twitch/OBS setting (title, tags, category, anything else), it MUST be surfaced on the browser dashboard in the same change.** The dashboard exists so David never has to open Twitch or OBS to confirm something is set correctly - it's the single centralised view. Concretely: add the value to the daemon's dashboard-facing state (`self._current_*` in `daemon.py`, cleared in `_on_no_game`), include it in the `status_file.write_status(...)` call in `_print_heartbeat`, and add a row to `INDEX_HTML` in `dashboard_server.py` (both the static row markup and the JS `tick()` function that fills it in). Applied for Title and Tags (2026-07-18) - see `_current_title`/`_current_tags` in `daemon.py` and the Title/Tags rows in `dashboard_server.py`. Applied for the audio privacy guard (2026-07-28) - see the Audio row in `dashboard_server.py` and the safety rule above.

## Never kill a live running instance (rule)

**If StreamPilot is running while Claude is editing this repo (real stream may be live), NEVER kill/stop the process to "apply changes" or to test something** - that stops the actual OBS stream and ends the VOD mid-session. Before running `run.bat`, `python src/streampilot.py start`, or any command that would start a second instance, or before using `taskkill`/`Stop-Process` on `pythonw`/`python` for this repo: check first (`Get-Process pythonw -ErrorAction SilentlyContinue`, or tail the newest `data/logs/*.log`, or `curl http://localhost:8765/status.json`). If it's already running: **use the hot-reload trigger instead** - touch/create `data/state/reload.trigger` once the edit is fully wired up (see hot-reload section below). This restarts the process in place (adopts the existing session via `_reconcile_existing_session()`) without ending the stream. Ask David before doing anything that would stop the stream (killing the process, `run.bat` double-launch, etc.) if hot-reload genuinely can't apply the change (e.g. a change to `run.bat` itself, which isn't watched).

## Always specify encoding='utf-8' on file I/O (rule, added 2026-07-21)

**Every `open()` call touching `config.json`, `status.json`, or any file that could ever hold non-ASCII text (emoji, names, etc.) must pass `encoding='utf-8'` explicitly.** Windows' default text encoding is the system codepage (cp1252 here), not UTF-8. Without the explicit arg, reading a file containing literal UTF-8 multi-byte sequences (not `\uXXXX`-escaped) raises `UnicodeDecodeError`. **Incident (2026-07-21):** adding a per-game `emoji` field to `config.json` crashed the live daemon on the very next hot-reload - `config.py::load()`'s `open(path, 'r')` had no encoding, so `json.load()` blew up on the emoji bytes. Invisible under `pythonw` (stderr to devnull) - the process just silently died, same failure shape as the 2026-07-19 psutil incident below. Fixed in `config.py` and `status_file.py`; regression test in `tests/test_config.py::test_load_handles_non_ascii_unicode_in_config`. `hot_reload.py` already did this correctly (`open(path, "r", encoding="utf-8")`)
- match that pattern in any new file I/O.

## Status/state field design (rule, added 2026-07-25)

**A status field shown on the dashboard must only ever encode current physical truth, never a transient "an action was just taken" event.** A polled UI (the dashboard reads `status.json` once a poll cycle) can only show a label for as long as it survives to the next poll - a one-cycle "I just corrected this" annotation is either invisible (overwritten before anyone looks) or, worse, asymmetric if only one direction of the correction gets a label and the other doesn't. **Incident:** SABnzbd's status field showed `"REPAUSED"` for exactly one heartbeat after the daemon auto-paused a drifted SABnzbd, but there was no matching `"UNPAUSED"` for the resume direction (resume happens synchronously on toggle-off, not via a heartbeat correction) - David never saw the label he expected and the asymmetry itself was the tell that the design was wrong, not just the wording. Fixed by collapsing `sab_str` in `daemon.py::_classify()` to plain physical states only (`Running`/`Paused`, `Disabled`/`Unreachable` for connectivity, `(manual)` suffix for mode) - correction *events* stay in the log line that triggers them (`log.warning(...)` in `_print_heartbeat`), never the polled state field. **Applies to any future dashboard row:** if you're about to add a value like `"JUST DID X"` to a `_classify()`-style status string, put it in the log instead and keep the field itself to states that are true for as long as they're displayed.

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
