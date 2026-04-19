# StreamPilot - Ideas and TODOs

## Pending

### Quick wins

- **Bug: SABnzbd not paused while streaming** - SABnzbd should be paused when a stream starts and resumed when it stops (bandwidth contention). SABnzbd has a REST API - use it to pause/resume.

### Logging overhaul (batch together)
- Separate, timestamped log files per run - like SBS_Download (`data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`), not all appended to one `streampilot.log`
- Every `.bat` script must produce a log - currently `status.bat` appends to one file, others produce nothing. Should be clear from logs which script was run.
- Remove indentation from log output (current logs have leading whitespace)

### Add-game UX (batch together)
- Replace numbered window list with arrow-key interactive selector - see RivalsVidMaker (`C:\Users\David\GitHubRepos\RivalsVidMaker`) for the pattern. Show list once only, selectable
- Auto-detect game name from the window title column (2nd column in detected windows, e.g. "Marvel Rivals" from `Marvel-Win64-Shipping.exe | Marvel Rivals`). Use that to search Twitch automatically. only fall back to manual Game ID entry as last resort. ALWAYS Only ask user to confirm before locking in.
- Clarify the "Game name (for display)" prompt - user didn't understand it was used for Twitch search. Reword or show the intent inline
- Fix Twitch game search - "Marvel Rivals" returned no results. Implement fuzzy/partial matching or use Twitch's search API more robustly
- Document or surface where to get Twitch Game IDs when manual entry is needed

### Bat script behaviour
- All `.bat` scripts should stay open after completion so user can read output and copy to Claude. `add-game` closes immediately. Use `cmd /k` or add a `pause` at end
- `add-game` prompts "Make sure your game is running" twice (once before `pause`, once after) - deduplicate

### Status script
- Make `status.bat` more robust when OBS or SABnzbd are not running (currently unclear output/errors)
- Consider renaming `status` to `check` or `dry-run` - its value is as a no-stream diagnostic tool that validates detection logic without actually streaming


### System tray icon
- Run StreamPilot in the system tray instead of a CLI window, with right-click exit menu. Use `pystray` + `Pillow` for the icon
- Possible extensions: show status (idle/streaming/game detected), balloon tip notifications, stop from tray

### Process / lifecycle
- LOW PRIORITY: `streampilot stop` command - send stop signal to running daemon process
- LOW PRIORITY: Auto-start with Windows (Task Scheduler entry)
- MED PRIORITY: Auto-start Steam on daemon launch - full workflow becomes: start StreamPilot, launch game, nothing else manual

### Game / streaming features
- LOW PRIORITY: Set Twitch tags per game (currently tags are global) 
- LOW PRIORITY: Windows toast notification for unknown game detected ("Run 'streampilot config add-game'")