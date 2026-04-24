# StreamPilot - Ideas and TODOs

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently)*

## P1 - Do next

- **Logging overhaul** (HIGH PRIORITY - batch all sub-items together):
  - Every log line must start with a uniform timestamp prefix: `[YYYY-MM-DD HH:MM:SS,mmm]`
  - Log file and terminal output must be 1:1 equivalent - what appears on screen goes to the log file, same format, same lines
  - Separate, timestamped log files per run - like SBS_Download (`data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`), not all appended to one file
  - Every `.bat` script must produce a log - should be clear from logs which script was run
  - Remove indentation from log output (current logs have leading whitespace)

- **Auto-relaunch Steam if closed** - same pattern as OBS auto-launch (`daemon.py:51-59`): check psutil, read optional `steam.exe_path` from config (default `C:\Program Files (x86)\Steam\steam.exe`), `subprocess.Popen([exe_path], cwd=steam_dir)`. No admin needed. ~5 lines.

## Quick wins

- **Status heartbeat - remove OBS field** - `Streaming: Marvel Rivals | OBS: Live` is redundant; OBS state is directly implied by Streaming state. Remove `OBS: X` field from the heartbeat line to reduce noise.
- **OBS window string double space cleanup** - config has `Marvel Rivals  :UnrealWindow:...` (double space). Confirm the correct string from the OBS Game Capture dropdown and clean up. Low risk. (Note: program works despite this.)

## System tray (do after status heartbeat)

Two distinct jobs - both matter:

1. **Pre-game confirmation** - before launching a game, David can glance at the tray and know the daemon is active. This is the window where the terminal may be hidden or minimised.
2. **Close-to-minimize / accidental kill resistance** - closing the terminal window should NOT kill the daemon. Closing the window minimizes to tray instead (Spotify/Discord model - see `Close button should minimize` setting). Without this, one accidental terminal close leaves SABnzbd paused and stream potentially still running with no watchdog.

Implementation:
- `pystray` + `Pillow` for tray icon
- **Dynamic icon** - tick (all OK) or cross (issue) visible in taskbar while alt-tabbed to Discord or elsewhere
- Icon ready: `assets/StreamPilotIconNoBG.ico` (transparent background) + `assets/StreamPilotIconOriginal.png`
- Right-click menu: Status, Stop StreamPilot (clean shutdown)
- On terminal close (`WM_DELETE_WINDOW` or SIGINT from X button): hide window, keep daemon running in background
- Tray tooltip: current state (Streaming: Marvel Rivals / Idle)
- The tray icon covers the bookends (pre-game + close guard); the heartbeat log covers in-game monitoring from second screen. Both are needed.

**Note on full-screen coverage:** tray IS covered when game is fullscreen on primary monitor, and Windows may not show it on the secondary. This is expected - tray's job is pre-game and post-game, not in-game. Heartbeat on second screen covers in-game.

## Robustness (golden path stability)

- **Pre-flight checks** - before connecting to OBS or SABnzbd, verify they are actually running. Check process list first; log a clear warning and skip if not found. Observed: starting SP with SABnzbd not running caused a ~13s hang before the connection error was logged (Max retries exceeded). Should fail fast with a clear "SABnzbd not running" message instead.
- **Handle OBS closing while running** - detect OBS process exit and respond gracefully. Many state combinations need thought: OBS closed intentionally, OBS crashed, OBS restarted externally. All relevant program statuses should be monitored and handled - needs design session before implementing.
- **Close OBS when StreamPilot exits** - when the daemon shuts down cleanly, OBS should also close automatically. Ensures no zombie OBS session remains after StreamPilot stops.

## Live status improvements

- **More frequent status updates** - current heartbeat fires every ~10s. David wants ~3-5s for a "live" feel. Options: (a) lower the heartbeat interval, (b) open a dedicated second terminal that clears and reprints status every 2-3s. Needs thought on which UX is better.
- **Check audio and OBS settings** - verify game being streamed is in "Application Audio Output Capture" list and correctly configured. Could be checked or set automatically, similar to the game capture window check.
- **Windows Terminal on right screen** - for this program only, open maximised on the right monitor by default. Windows Terminal supports per-profile config (`initialPosition`, `launchMode` in settings JSON) - investigate feasibility.

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Stretch goals

- **Dashboard web UI** - replace the batch script setup flow with a browser-based dashboard. Better UX for config, game management, and live status. Would replace the current .bat launcher and add-game wizard. Ask claude best way to do , use https://claude.ai/design ? use https://github.com/nextlevelbuilder/ui-ux-pro-max-skill?

## Docs overhaul

- Review all docs (README, CLAUDE.md, IDEAS.md, any setup guides) - consolidate, remove duplication, tighten language. No data loss. Reduce total doc surface area. Specific pain point: README's linear step format doesn't reflect how the program actually works - particularly SABnzbd integration, which isn't a sequential setup step but a background behaviour. Restructure around how the program behaves, not a setup checklist.
- Add icon to readme similar to `# <img width="24px" src="./Logo/256.png" alt="Sonarr"></img>` like https://github.com/Sonarr/Sonarr does

## Medium priority

- Auto-start with Windows (Task Scheduler entry)
- Windows toast notification for unknown game detected
- Brainstorm session with Claude - get Claude to generate a wide list of StreamPilot improvement ideas (separate dev session, purely generative, no implementation)

## Low priority

- LOW: Set Twitch tags per game (currently tags are global)
- LOW: SABnzbd per-game config for offline games - in config, specify games that SHOULDN'T pause SAB. Only multiplayer games need SAB paused; offline/single-player games should leave SAB running. No offline games currently, but design for it.
