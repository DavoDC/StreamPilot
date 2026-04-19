# StreamPilot - Execution Plan

Generated: 2026-04-19

| Phase | Focus | Items |
|-------|-------|-------|
| 1 | Bat script fixes + Logging overhaul | cmd/k, deduplicate prompt, per-run logs, every bat logs, remove indentation |
| 2 | Status script | Robustness (OBS/SABnzbd offline), rename decision |
| 3 | Add-game UX overhaul | Arrow-key selector, auto-detect game name, fix Twitch search, clarify prompt, manual ID docs |
| 4 | System tray icon | pystray icon, right-click menu, real-time status, balloon tips |
| 5 | Process lifecycle + low-priority | Auto-start Steam, stop command, Task Scheduler autostart, per-game tags, unknown-game toast |

---

## Phase 1 - Bat Script Fixes + Logging Overhaul

- [ ] All `.bat` scripts must stay open after completion - use `cmd /k` (not `pause`)
- [ ] `add-game` wizard prints "Make sure your game is running" twice - deduplicate
- [ ] Replace single appended `streampilot.log` with timestamped per-run files: `data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log`
- [ ] Every `.bat` script produces its own timestamped log - log header identifies which script ran
- [ ] Remove leading whitespace indentation from log output (fix at Python formatter level)

**Session prompt:**

```
You are working on StreamPilot, a Python CLI daemon at C:\Users\David\GitHubRepos\StreamPilot that auto-manages OBS streaming when a known game launches. Read CLAUDE.md and all files in scripts/ before starting.

Implement ALL of the following bat script and logging fixes:

1. cmd/k fix: Every .bat script must stay open after completion so the user can read output. Use `cmd /k`. Check and fix all scripts in scripts/.

2. Deduplicate prompt: The add-game wizard currently prints "Make sure your game is running" twice (once before a pause, once after). Remove the duplicate.

3. Per-run log files: Replace the single appended streampilot.log with timestamped per-run files at data/logs/streampilot_YYYY-MM-DD_HH-MM-SS.log. Pattern-copy from C:\Users\David\GitHubRepos\SBS_Download - find how it creates per-run log files and adapt that pattern.

4. Every bat script produces a log: Each bat invocation must write its own timestamped log. The log header must identify which script was run.

5. Remove log indentation: Current log output has leading whitespace. Fix at the Python logger formatter level in src/.

Run scripts\run-tests.bat after changes and confirm tests pass.

After finishing the work, update the Claude_Workspace repo with all important learnings, patterns, and improvements from this session.
```

---

## Phase 2 - Status Script Robustness + Rename Decision

- [ ] Make `status.bat` / `streampilot status` handle OBS-not-running and SABnzbd-not-running gracefully with clear messages
- [ ] Decide and implement: rename `status` to `check` or `dry-run` (or keep and add clarifying docstring) - update all references

**Session prompt:**

```
You are working on StreamPilot, a Python CLI daemon at C:\Users\David\GitHubRepos\StreamPilot. Read CLAUDE.md, src/streampilot.py, and scripts/status.bat before starting.

Implement ALL of the following status script improvements:

1. Robustness: streampilot status currently produces unclear output or exceptions when OBS or SABnzbd are not running. Make it handle both cases gracefully - print clear "OBS not reachable" and "SABnzbd not running" messages rather than throwing.

2. Rename decision: The command's real value is as a no-stream diagnostic tool that validates detection without actually streaming. Evaluate whether to rename it from `status` to `check` or `dry-run`. Make a firm decision, implement it, and update all references: CLI entry point, bat script filename, CLAUDE.md, README.md, docs/. Do not leave it as a "consider" - commit to one name. Add a one-line docstring explaining its diagnostic role regardless of final name.

Run scripts\run-tests.bat after changes and confirm tests pass.

After finishing the work, update the Claude_Workspace repo with all important learnings, patterns, and improvements from this session.
```

---

## Phase 3 - Add-Game UX Overhaul

- [ ] Replace numbered window list with arrow-key interactive selector (pattern-copy from RivalsVidMaker)
- [ ] Auto-detect game name from window title column; use it to search Twitch automatically
- [ ] Fix Twitch game search - "Marvel Rivals" returned no results; implement fuzzy/partial matching
- [ ] Clarify "Game name (for display)" prompt - user didn't understand its role in Twitch search
- [ ] Surface where to get Twitch Game IDs for manual fallback (print URL in wizard)

**Session prompt:**

```
You are working on StreamPilot, a Python CLI daemon at C:\Users\David\GitHubRepos\StreamPilot. The `streampilot config add-game` command is the wizard for registering a new game. Read CLAUDE.md, src/streampilot.py, and src/twitch_client.py before starting.

Implement ALL of the following add-game UX improvements:

1. Arrow-key interactive selector: Replace the numbered window list with an arrow-key interactive selector. Pattern-copy from C:\Users\David\GitHubRepos\RivalsVidMaker - find the selector implementation there and adapt it. Show the list once only; user navigates with arrow keys and presses Enter to confirm.

2. Auto-detect game name: The detected windows list has the format `Executable | Window Title` (e.g. `Marvel-Win64-Shipping.exe | Marvel Rivals`). Extract the window title column as the candidate game name and use it to search Twitch automatically. Only fall back to manual Game ID entry as a last resort. Always confirm with the user before locking in.

3. Fix Twitch game search: "Marvel Rivals" returns no results. Investigate the search call in src/twitch_client.py. Use Twitch's `search/categories` endpoint and implement partial/fuzzy matching - try progressively shorter substrings if exact match fails. Show top 3-5 results and let the user pick.

4. Clarify display name prompt: Reword or restructure the "Game name (for display)" prompt so the user understands it drives the Twitch search. Prefer showing the auto-detected name and asking for confirmation rather than a blank prompt.

5. Manual Game ID fallback: When the user must enter a Twitch Game ID manually, print the lookup URL inline in the wizard (e.g. twitchapps.com/twitchid or Twitch dev console). Do not rely on docs alone.

Run scripts\run-tests.bat after changes and confirm tests pass.

After finishing the work, update the Claude_Workspace repo with all important learnings, patterns, and improvements from this session.
```

---

## Phase 4 - System Tray Icon

- [ ] Run StreamPilot in the system tray using `pystray` + `Pillow`
- [ ] Right-click menu with at minimum: Exit (clean daemon stop)
- [ ] Status indication in tray: idle / streaming / game detected (icon or tooltip, updated in real time)
- [ ] Balloon tip notifications for key events: stream started, game switched, stream stopped

**Session prompt:**

```
You are working on StreamPilot, a Python CLI daemon at C:\Users\David\GitHubRepos\StreamPilot. Read CLAUDE.md and src/daemon.py before starting.

Implement a system tray icon using pystray and Pillow:

1. Tray icon: When the StreamPilot daemon starts, show a system tray icon. Use pystray + Pillow. Generate the icon programmatically (simple coloured circle or text icon is fine - no asset file needed).

2. Right-click menu: Minimum required: "Exit" that cleanly stops the daemon. Preferred additions: "Stop Stream", "Status" shown as a greyed-out label.

3. Real-time status: Show current daemon state (idle / streaming / game detected) via the tray tooltip or a different icon colour. Update it in the existing poll loop in daemon.py.

4. Balloon tip notifications: Use pystray's notify() (or win10toast as fallback) to fire balloon tips on: stream started, game switched, stream stopped.

Add pystray and Pillow to pyproject.toml. The daemon must degrade gracefully if tray initialisation fails (log a warning and continue running headlessly - never crash).

Run scripts\run-tests.bat after changes and confirm tests pass.

After finishing the work, update the Claude_Workspace repo with all important learnings, patterns, and improvements from this session.
```

---

## Phase 5 - Process Lifecycle + Low-Priority Features

- [ ] MED: Auto-start Steam on daemon launch (opt-in config flag)
- [ ] LOW: `streampilot stop` command - verify fully implemented or complete (PID file approach)
- [ ] LOW: `streampilot install-autostart` / `remove-autostart` via Windows Task Scheduler
- [ ] LOW: Per-game Twitch tags (`"twitch_tags"` list in config; set when switching category)
- [ ] LOW: Windows toast notification for unknown game detected - prefer pystray if Phase 4 is done, else win10toast

**Session prompt:**

```
You are working on StreamPilot, a Python CLI daemon at C:\Users\David\GitHubRepos\StreamPilot. Read CLAUDE.md and src/daemon.py before starting. Note: a pystray system tray icon was added in a prior session - prefer its notify() for any new notifications.

Implement ALL remaining low/medium-priority improvements:

1. Auto-start Steam (MED): When the daemon starts, auto-launch Steam if it is not already running. Controlled by an opt-in config flag: `"auto_start_steam": true` in config.json. Update config.py to recognise this flag. Full target workflow: start StreamPilot, launch game, nothing else manual.

2. streampilot stop command: Check whether src/streampilot.py fully implements stop (sends a real signal to the running daemon). If it only stubs it, complete it: write a PID file to data/ on daemon start, read and signal it on stop. Clean up the PID file on exit.

3. Auto-start with Windows: Add two CLI commands - `streampilot install-autostart` and `streampilot remove-autostart`. Use the Windows Task Scheduler (subprocess + schtasks.exe) to create/delete a task that runs StreamPilot on user login. Document both commands in README.md.

4. Per-game Twitch tags: Add an optional `"twitch_tags": ["tag1", "tag2"]` field to each game entry in config.json. When setting the Twitch category in twitch_client.py, also apply the tags if provided. Update the add-game wizard to optionally prompt for tags (skippable).

5. Toast notification for unknown game: When an unknown game is detected in daemon.py, fire a notification: "Unknown game detected - run 'streampilot config add-game'". Use pystray notify() if the tray is running, otherwise fall back to win10toast. Never crash if notifications are unavailable.

Run scripts\run-tests.bat after changes and confirm tests pass.

After finishing the work, update the Claude_Workspace repo with all important learnings, patterns, and improvements from this session.
```

---

## Ordering Notes

- Phase 1 before Phase 2: `status.bat` gets its logging fixed in Phase 1 (per-run files); Phase 2 adds robustness on top of the correct baseline.
- Phase 1 before Phase 3: bat script `cmd /k` baseline must be correct before the add-game wizard rewrite touches the same scripts.
- Phase 4 before Phase 5: Phase 5 reuses pystray notify() added in Phase 4. If Phase 4 is skipped, Phase 5 falls back to win10toast - the prompt handles this.
- The rename decision in Phase 2 (status -> check/dry-run) is resolved before any later phase could reference the command by name.
- `streampilot stop` appears in CLAUDE.md's CLI table as existing but in IDEAS.md as LOW priority - Phase 5 treats it as "verify or complete."
