# StreamPilot - Ideas and TODOs

> Follow `ClaudeOnly\memory\processes\ideas-md-workflow.md` when progressing this program.

## Quick wins

- **run.bat opens cmd instead of Windows Terminal** - UAC elevation via `Start-Process` spawns a plain cmd window. User prefers Windows Terminal (`wt.exe`). Change elevation command to: `Start-Process -FilePath wt.exe -ArgumentList "cmd /k cd /d \"%~dp0..\" && python src\streampilot.py start" -Verb RunAs`.
- **OBS window string double space cleanup** - config has `Marvel Rivals  :UnrealWindow:...` (double space). Game capture works despite this, so OBS appears lenient. Confirm the correct string from the OBS Game Capture dropdown and clean up config. Low risk.
- **Remove incorrect "streampilot start" message** - add-game.bat outputs "Added! Run 'streampilot start' to begin monitoring." but StreamPilot uses .bat scripts, not a CLI command. Replace with correct bat-script instruction or remove entirely.
- **Bat scripts must stay open** - all `.bat` scripts should stay open after completion so user can read output. `add-game` closes immediately. Use `cmd /k` or add `pause` at end.
- **Deduplicate add-game prompt** - `add-game` prompts "Make sure your game is running" twice (once before `pause`, once after). Remove duplicate.

## Robustness (golden path stability)

- **Pre-flight checks** - before connecting to OBS or SABnzbd, verify they are actually running. Currently program tries to connect regardless, causing silent failures or confusing errors. Check process list first; log a clear warning and skip if not found.
- **Handle OBS closing while running** - if OBS exits mid-session, the program currently does not react. Should detect the process exit and respond gracefully (log it, attempt restart, or surface a clear error).

## Add-game UX (batch together)

- Replace numbered window list with arrow-key interactive selector - see RivalsVidMaker (`C:\Users\David\GitHubRepos\RivalsVidMaker`) for the pattern. Show list once only, selectable.
- Auto-detect game name from the window title column (2nd column in detected windows, e.g. "Marvel Rivals" from `Marvel-Win64-Shipping.exe | Marvel Rivals`). Use that to search Twitch automatically. Only fall back to manual Game ID entry as last resort. Always ask user to confirm before locking in.
- Fix Twitch game search - "Marvel Rivals" returned no results. Implement fuzzy/partial matching or use Twitch's search API more robustly.
- Clarify the "Game name (for display)" prompt - user didn't understand it was used for Twitch search. Reword or show intent inline.
- Document or surface where to get Twitch Game IDs when manual entry is needed.

## Logging overhaul (batch together)

- Separate, timestamped log files per run - like SBS_Download (`data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`), not all appended to one `streampilot.log`.
- Every `.bat` script must produce a log - currently `status.bat` appends to one file, others produce nothing. Should be clear from logs which script was run.
- Remove indentation from log output (current logs have leading whitespace).

## Status script

- Make `status.bat` more robust when OBS or SABnzbd are not running (currently unclear output/errors).
- Consider renaming `status` to `check` or `dry-run` - its value is as a no-stream diagnostic tool that validates detection logic without actually streaming.

## Security

- **Full security review** - analyse all attack surfaces: config.json stores OAuth token in plaintext, OBS WebSocket password in plaintext, SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level for a local desktop tool vs. hardening options (e.g. OS keychain, env vars).

## Low priority

- LOW: Remove `setup-config.bat` - it's redundant. It copies the example config and then opens the folder anyway, so the user still has to manually edit the file. Easier to just tell the user to open File Explorer, copy `config.example.json` to `config.json`, and edit it directly. Remove the script and update the README.
- MED: Auto-start Steam on daemon launch - full workflow becomes: start StreamPilot, launch game, nothing else manual.
- LOW: `streampilot stop` command - send stop signal to running daemon process.
- LOW: Auto-start with Windows (Task Scheduler entry).
- LOW: System tray icon - run StreamPilot in system tray instead of CLI window, with right-click exit menu. Use `pystray` + `Pillow`. Possible extensions: show status (idle/streaming/game detected), balloon tip notifications, stop from tray.
- LOW: Set Twitch tags per game (currently tags are global).
- LOW: Windows toast notification for unknown game detected ("Run 'streampilot config add-game'").
