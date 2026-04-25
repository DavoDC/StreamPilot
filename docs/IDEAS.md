# StreamPilot - Ideas and TODOs

> **STOP - DO NOT add work here. StreamPilot is feature-complete for current use. Primary focus is now AudioManager. Only return here for critical bugs.**

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## P0 - Blocking bugs

*(none currently)*

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

## Live status improvements

- **Check audio and OBS settings** - verify game being streamed is in "Application Audio Output Capture" list and correctly configured. Could be checked or set automatically, similar to the game capture window check.
- **Windows Terminal on right screen** - for this program only, open maximised on the right monitor by default. Windows Terminal supports per-profile config (`initialPosition`, `launchMode` in settings JSON) - investigate feasibility.

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Stretch goals

- **Dashboard web UI** - replace the batch script setup flow with a browser-based dashboard. Better UX for config, game management, and live status. Would replace the current .bat launcher and add-game wizard. Research best framework before starting - lightweight options preferred (no heavy Node stack). Consider https://claude.ai/design for UI mockups first.

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
