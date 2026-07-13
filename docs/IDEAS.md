# StreamPilot - Ideas and TODOs

**Status:** Feature-complete for current use. AudioManager MVP now complete, so StreamPilot can receive enhancements again. Critical bugs always welcome.

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently - OBS window staleness fixed: heartbeat now verifies + reapplies.
Twitch-auth-silently-looks-like-"not found" and the 20-window add-game cap were
both fixed 2026-07-13, see HISTORY.md)*

## Robustness follow-ups (found during 2026-07-13 code review, not yet needed)

- **add-game window picker still can't search/filter** - raised the cap 20->40 as
  an immediate fix, but on a very busy desktop it could still truncate. If this
  ever bites, swap `questionary.select` for `questionary.autocomplete` (built-in
  fuzzy text filter) instead of raising the cap further.
- **Twitch token expiry has no proactive warning during normal daemon operation**
  - add-game now validates and warns up front (fixed), but `daemon.py`'s
    `start()` also calls `self.twitch.validate()` (line ~102) without checking
    the result or logging clearly if it fails. Worth a heartbeat-visible warning
    if the token goes stale mid-session, same pattern as the SABnzbd/OBS checks.

## P1 - AudioManager (next major feature - start after QOL batch is done)

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

## Homeostasis - Keep Things in Right State

**Concept:** Regularly check that critical services are in the state StreamPilot expects, and automatically bring them back if they drift.

**Shipped (in heartbeat, every 2s when game active):**
- **OBS Game Capture window** - verified, reapplied if wrong. Shows `OBS Window: REAPPLIED` + ISSUE.
- **SABnzbd pause state** - auto-repauses if found running. Shows `SABnzbd: REPAUSED` + ISSUE.
- **OBS WebSocket connection** - `is_connected()` check before all OBS calls; reconnects if WebSocket dropped.
- **Stream state** - if WebSocket alive but stream stopped, restarts stream. Shows `Stream: RESTARTED` + ISSUE.

**Remaining (needs separate design session):**
- **OBS process crash** - detect OBS.exe exit and restart the process. Needs design: OBS crash vs intentional close vs WebSocket timeout. Subprocess monitoring, not a heartbeat-pattern fix.

**Design note:** The heartbeat pattern (poll every 2s, correct inline, flag ISSUE) works for any correction where the target service's API is reachable. OBS process restart requires a different mechanism (process supervision) - deliberately deferred.

## Live status improvements

- **Check audio and OBS settings** - verify game being streamed is in "Application Audio Output Capture" list and correctly configured. Could be checked or set automatically (same pattern as the game capture window check, which is already done in the heartbeat).
- **Windows Terminal on right screen** - for this program only, open maximised on the right monitor by default. Windows Terminal supports per-profile config (`initialPosition`, `launchMode` in settings JSON) - investigate feasibility.

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Stretch goals

- **Setup/config web UI** - replace the batch-script setup flow (config editing, add-game wizard) with a browser-based UI. NOTE: the live-status half of this idea shipped 2026-07-13 as `scripts/dashboard.bat` (a local web dashboard) - see HISTORY.md; this item is now scoped to config/setup only, not live status.

## Docs overhaul

- Review all docs (README, CLAUDE.md, IDEAS.md, any setup guides) - consolidate, remove duplication, tighten language. No data loss. Reduce total doc surface area. Specific pain point: README's linear step format doesn't reflect how the program actually works - particularly SABnzbd integration, which isn't a sequential setup step but a background behaviour. Restructure around how the program behaves, not a setup checklist.
- Add inline icon to the README heading - same pattern as Sonarr's README (`<img>` tag next to the `#` heading). Icon assets are already in `assets/`.

## Medium priority

- **Auto-start with Windows** - Task Scheduler entry to launch StreamPilot on login.
- **Windows toast notification for unknown game** - when an unrecognised process is detected, surface a Windows toast so it can be added via the add-game wizard without switching windows.
- **Brainstorm session with Claude** - dedicated session to generate a wide list of improvement ideas for StreamPilot. Purely generative, no implementation. Run as a separate `/dev-session`.

## Low priority

- **Set Twitch tags per game** - currently tags are global. Allow per-game tag overrides in config.
- **SABnzbd per-game config for offline games** - in config, flag games that SHOULDN'T pause SAB. Only multiplayer games need SAB paused; offline/single-player games should leave it running. No offline games currently, but worth designing for.
