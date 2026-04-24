# StreamPilot - Ideas and TODOs

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently)*

## P1 - Do next

*(none currently)*

## Needs real-environment test

- **Verify game-per-VOD in live session** - launch a game, confirm stream starts, launch a second known game, confirm stream stops and restarts (new VOD). Feature is implemented and unit-tested but not yet verified end-to-end.

## Quick wins

- **Delete status.bat and setup-config.bat** - do together in one commit, one README update covers both.
  - `scripts/status.bat` - redundant once pre-flight checks land; diagnostic value covered by main-program startup checks.
  - `scripts/setup/setup-config.bat` - copies example config then pauses; user still edits manually. Update README Step 3 to: "Copy `config\config.example.json` to `config\config.json` and open it to fill in your settings."
- **OBS window string double space cleanup** - config has `Marvel Rivals  :UnrealWindow:...` (double space). Confirm the correct string from the OBS Game Capture dropdown and clean up. Low risk.
- **Bat scripts must stay open** - all `.bat` scripts should use `cmd /k` or `pause` so output is readable. `add-game.bat` currently closes immediately.
- **Auto-relaunch Steam if closed** - same pattern as OBS auto-launch (`daemon.py:51-59`): check psutil, read optional `steam.exe_path` from config (default `C:\Program Files (x86)\Steam\steam.exe`), `subprocess.Popen([exe_path], cwd=steam_dir)`. No admin needed. ~5 lines.

## System tray (P1 - do after status heartbeat)

Two distinct jobs - both matter:

1. **Pre-game confirmation** - before launching a game, David can glance at the tray and know the daemon is active. This is the window where the terminal may be hidden or minimised.
2. **Close-to-minimize / accidental kill resistance** - closing the terminal window should NOT kill the daemon. Closing the window minimizes to tray instead (Spotify/Discord model - see `Close button should minimize` setting). Without this, one accidental terminal close leaves SABnzbd paused and stream potentially still running with no watchdog.

Implementation:
- `pystray` + `Pillow` for tray icon
- Icon ready: `assets/StreamPilotIconNoBG.ico` (transparent background) + `assets/StreamPilotIconOriginal.png`
- Right-click menu: Status, Stop StreamPilot (clean shutdown)
- On terminal close (`WM_DELETE_WINDOW` or SIGINT from X button): hide window, keep daemon running in background
- Tray tooltip: current state (Streaming: Marvel Rivals / Idle)
- The tray icon covers the bookends (pre-game + close guard); the heartbeat log covers in-game monitoring from second screen. Both are needed.

**Note on full-screen coverage:** tray IS covered when game is fullscreen on primary monitor, and Windows may not show it on the secondary. This is expected - tray's job is pre-game and post-game, not in-game. Heartbeat on second screen covers in-game.

## Robustness (golden path stability)

- **Pre-flight checks** - before connecting to OBS or SABnzbd, verify they are actually running. Check process list first; log a clear warning and skip if not found. Observed: starting SP with SABnzbd not running caused a ~13s hang before the connection error was logged (Max retries exceeded). Should fail fast with a clear "SABnzbd not running" message instead.
- **Handle OBS closing while running** - detect OBS process exit and respond gracefully (log it, attempt restart, or surface a clear error).
- **SABnzbd must resume on game stop or program stop** - when StreamPilot detects the game has closed, OR when StreamPilot itself exits, automatically resume SABnzbd (undo any pause/throttle it applied). Currently SABnzbd can be left paused if StreamPilot exits uncleanly.

## Logging overhaul (batch together)

- Separate, timestamped log files per run - like SBS_Download (`data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`), not all appended to one file.
- Every `.bat` script must produce a log - should be clear from logs which script was run.
- Remove indentation from log output (current logs have leading whitespace).
- Every entry in log should start with timestamp, looks weird when some don't have

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Stretch goals

- **Dashboard web UI** - replace the batch script setup flow with a browser-based dashboard. Better UX for config, game management, and live status. Would replace the current .bat launcher and add-game wizard. Ask claude best way to do , use https://claude.ai/design ? use https://github.com/nextlevelbuilder/ui-ux-pro-max-skill? 

## Docs overhaul

- Review all docs (README, CLAUDE.md, IDEAS.md, any setup guides) - consolidate, remove duplication, tighten language. No data loss. Reduce total doc surface area. Specific pain point: README's linear step format doesn't reflect how the program actually works - particularly SABnzbd integration, which isn't a sequential setup step but a background behaviour. Restructure around how the program behaves, not a setup checklist.

## Low priority

- LOW: Auto-start with Windows (Task Scheduler entry).
- LOW: Set Twitch tags per game (currently tags are global).
- LOW: Windows toast notification for unknown game detected.
