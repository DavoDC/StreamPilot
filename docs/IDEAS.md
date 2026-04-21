# StreamPilot - Ideas and TODOs

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently)*

## P1 - Do next

- **Game-per-VOD** - see Architecture section below for full spec. This is the core direction for the program; do before investing heavily in mid-session switch behaviour.
- **Add-game UX** - see section below. Do before adding Dead by Daylight as a second game - the wizard is rough enough that fixing it first is worth it. Marvel Rivals and Dead by Daylight are the two target games.

## Quick wins

- **Delete status.bat and setup-config.bat** - do together in one commit, one README update covers both.
  - `scripts/status.bat` - redundant once pre-flight checks land; diagnostic value covered by main-program startup checks.
  - `scripts/setup/setup-config.bat` - copies example config then pauses; user still edits manually. Update README Step 3 to: "Copy `config\config.example.json` to `config\config.json` and open it to fill in your settings."
- **OBS window string double space cleanup** - config has `Marvel Rivals  :UnrealWindow:...` (double space). Confirm the correct string from the OBS Game Capture dropdown and clean up. Low risk.
- **Remove incorrect "streampilot start" message** - `add-game.bat` outputs "Run 'streampilot start' to begin monitoring." StreamPilot uses .bat scripts, not a CLI command. Replace with correct bat-script instruction.
- **Bat scripts must stay open** - all `.bat` scripts should use `cmd /k` or `pause` so output is readable. `add-game.bat` currently closes immediately.
- **Deduplicate add-game prompt** - `add-game` prompts "Make sure your game is running" twice. Remove duplicate.
- **Auto-relaunch Steam if closed** - same pattern as OBS auto-launch (`daemon.py:51-59`): check psutil, read optional `steam.exe_path` from config (default `C:\Program Files (x86)\Steam\steam.exe`), `subprocess.Popen([exe_path], cwd=steam_dir)`. No admin needed. ~5 lines.

## Architecture - Game-per-VOD (P1 - see above)

Each game session = one VOD. This is the intended long-term model:

- When the monitored game process closes, StreamPilot ends the stream/recording automatically.
- When a new game is detected, a fresh stream starts with that game's config.
- **This eliminates mid-session switch complexity entirely** - no need to handle game changes mid-stream because streams are scoped to a single game session. The "mid-session switch" use case in CLAUDE.md is slated for removal, not improvement.

Implementation notes:
- Requires reliable game process exit detection (psutil already polls, just needs exit action)
- OBS: call StopRecord/StopStream on exit, StartRecord/StartStream on new game launch
- Config: no changes needed - each game entry already has its own Twitch/OBS settings
- Update CLAUDE.md "Key Behaviour" and use cases when this ships

## Add-game UX (batch together, P1 - see above)

- Replace numbered window list with arrow-key interactive selector - see RivalsVidMaker for pattern. Show list once only, selectable.
- Auto-detect game name from window title column (e.g. "Marvel Rivals" from `Marvel-Win64-Shipping.exe | Marvel Rivals`). Use that to search Twitch automatically. Only fall back to manual Game ID entry as last resort.
- Fix Twitch game search - "Marvel Rivals" returned no results. Implement fuzzy/partial matching or use Twitch search API more robustly.
- Clarify the "Game name (for display)" prompt - reword or show intent inline.
- Document or surface where to get Twitch Game IDs when manual entry is needed.

## System tray (P1 - do after status heartbeat)

Two distinct jobs - both matter:

1. **Pre-game confirmation** - before launching a game, David can glance at the tray and know the daemon is active. This is the window where the terminal may be hidden or minimised.
2. **Close-to-minimize / accidental kill resistance** - closing the terminal window should NOT kill the daemon. Closing the window minimizes to tray instead (Spotify/Discord model - see `Close button should minimize` setting). Without this, one accidental terminal close leaves SABnzbd paused and stream potentially still running with no watchdog.

Implementation:
- `pystray` + `Pillow` for tray icon
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

- **Dashboard web UI** - replace the batch script setup flow with a browser-based dashboard. Better UX for config, game management, and live status. Would replace the current .bat launcher and add-game wizard.

## Docs overhaul

- Review all docs (README, CLAUDE.md, IDEAS.md, any setup guides) - consolidate, remove duplication, tighten language. No data loss. Reduce total doc surface area. Specific pain point: README's linear step format doesn't reflect how the program actually works - particularly SABnzbd integration, which isn't a sequential setup step but a background behaviour. Restructure around how the program behaves, not a setup checklist.

## Low priority

- LOW: Auto-start with Windows (Task Scheduler entry).
- LOW: Set Twitch tags per game (currently tags are global).
- LOW: Windows toast notification for unknown game detected.
