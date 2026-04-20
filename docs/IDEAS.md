# StreamPilot - Ideas and TODOs

> MANDATORY: Read `ClaudeOnly\memory\processes\ideas-md-workflow.md` at session start before picking any item. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently)*

## P1 - Do next

- **Windows Terminal** - `run.bat` UAC elevation via `Start-Process` spawns a plain cmd window. Change to: `Start-Process -FilePath wt.exe -ArgumentList "cmd /k cd /d \"%~dp0..\" && python src\streampilot.py start" -Verb RunAs`
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

## Robustness (golden path stability)

- **Pre-flight checks** - before connecting to OBS or SABnzbd, verify they are actually running. Check process list first; log a clear warning and skip if not found.
- **Handle OBS closing while running** - detect OBS process exit and respond gracefully (log it, attempt restart, or surface a clear error).

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

## Logging overhaul (batch together)

- Separate, timestamped log files per run - like SBS_Download (`data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`), not all appended to one file.
- Every `.bat` script must produce a log - should be clear from logs which script was run.
- Remove indentation from log output (current logs have leading whitespace).

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Low priority

- LOW: Auto-start with Windows (Task Scheduler entry).
- LOW: System tray icon - run in tray with right-click exit, status display, balloon tip notifications. Needs `pystray` + `Pillow`.
- LOW: Set Twitch tags per game (currently tags are global).
- LOW: Windows toast notification for unknown game detected.
