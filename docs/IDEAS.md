# StreamPilot - Ideas and TODOs

**Status:** Actively enhanced (viewer-growth title/tags/emoji work shipped 2026-07-18/21). Critical bugs always welcome.

> MANDATORY: Run `/dev-session StreamPilot` to start work. That skill IS the workflow - it picks the top item, confirms scope, implements, tests, and closes out correctly. Fix P0 bugs first. Never work out of order.

## HIGHEST PRIORITY - Viewer Growth: Dynamic Stream Optimization! (added 2026-07-18)

**The problem:** Stream settings are static and generic. Title is "Davo Gaming", the
go-live text is "Davo went live!", and tags are a stale fixed list (ssf2, Fortnite,
oblivionremastered, etc.) that don't match whatever is actually being played. Twitch
discovery is driven by **category + title keywords + tags** - so a stale title and
mismatched tags actively suppress how many new viewers can find the stream. The program
already knows the exact game (it sets the category from `config.games[exe].name` on every
launch), so leaving the title and tags static is pure wasted signal.

**The key leverage (why this is cheap):** `twitch_client.set_game()` already sends a
`PATCH /helix/channels` on every game launch, but only includes `game_id`. Twitch's
"Modify Channel Information" endpoint accepts `game_id`, `title`, AND `tags` in that
**same single request** - so dynamic title + dynamic tags cost **ZERO extra API calls**.
Everything below rides on the PATCH that already fires.

**Shipped 2026-07-18** (see HISTORY.md): dynamic per-game title (`title_template` +
per-game `title` override) and dynamic per-game tags (`base_tags` + per-game `tags`),
both riding the existing category PATCH. Per-game emoji title suffix shipped 2026-07-21.
Remaining from this brainstorm:

1. **Title template variety / rotation (top remaining item - cheapest lever left)** -
   instead of the identical title every session, keep a small pool of templates per game
   (or global) and pick one per launch, e.g. `"Davo plays {game}!"`, `"{game} ranked
   grind!"`, `"Chill {game} w/ Davo"`. Keeps the channel looking fresh to repeat browsers.
   Cheap: just a list + random choice.
2. **Dynamic go-live notification text - NEEDS RESEARCH, not just implementation.**
   The "Davo went live!" text is normally a Twitch Creator Dashboard setting, not part of
   the Helix "Modify Channel Information" endpoint `set_channel_info` already uses -
   unclear whether this is settable via API at all. Confirm the endpoint exists before
   scoping this as a dev-session item.

### DEEPER INVESTIGATION - optimize later (own dev-session)

Broader "optimize the stream to attract viewers via the program" brainstorm - not quick,
worth a dedicated session:

- **Title/tag performance tracking** - log title + tag set alongside peak/avg viewer count
  per VOD (data already flows through the daemon), so over time we learn which titles and
  tags actually correlate with viewers. Turns guessing into evidence. Needs a small
  per-session stats log + a later analysis pass.
- **Auto-generate tags from game metadata** - pull genre/theme tags from IGDB (or Twitch's
  own category tag suggestions) so a newly added game gets good tags without manual config.
- **Trending / seasonal tag research** - periodically surface which tags are trending in a
  game's category and suggest additions.
- **Time/schedule-aware titles** - vary title by time of day or day of week
  (e.g. "Late night {game}", "Weekend {game} grind") for relevance.
- **Keyword hooks per game** - curated high-search-volume phrases per game
  (e.g. hero names, modes, patch names) baked into the title/tag pool.
- **Language/region tuning** - confirm `broadcaster_language` is set (also part of the same
  PATCH) and matches the tag strategy.
- **Tie-in with dashboard cover-art idea** - the game poster idea under "Dashboard UI
  improvements" pairs naturally with this: show the live title + tags on the dashboard so
  David can see at a glance exactly how the stream is presented to viewers.

*(Config schema for title/tags/emoji is documented in CLAUDE.md's Config section, not
duplicated here - it's shipped, not a plan.)*

## TIER 1 - OBS card text refinement (added 2026-07-28, David's feedback @ 99356d3)

**Scope: the OBS card's two rows only.** David is happy with the three-card layout, the colour coding and everything else ("really sleek"). The Twitch and SABnzbd cards are not in scope. Do not restyle them.

**What is wrong.** The rows currently read `Game Captured  Pal (Palworld-Win64-Shipping.exe)` and `Audio  safe (Palworld-Win64-Shipping.exe)`. Three separate problems:

1. **"Pal" is the OBS window title**, and it is useless. Window titles are unreliable identifiers: they get truncated, they change at runtime (loading screens, level names, match state), and they are localised. The exe is the stable identity, and critically it is the exact thing the audio guard matches on. Showing a title next to an exe invites the eye to compare two different kinds of thing.
2. **Green "safe" is decorative colour.** If the healthy state is coloured, the eye learns that colour is normal and stops treating it as a signal. Colour must be reserved for the case that needs attention.
3. **Brackets and the word "safe" are noise.** They wrap the one value that matters in punctuation and a redundant adjective. The top-level OK/ISSUE indicator already states safety for the whole program.

**The design.** Both rows show the bare exe, identical formatting, plain white, no brackets, no prefix word:

```
OBS
Video    Palworld-Win64-Shipping.exe
Audio    Palworld-Win64-Shipping.exe
```

`Game Captured` becomes `Video`, which David suggested and which is right for a reason worth stating: `Video` and `Audio` are the two halves of one stream, so the symmetric labels make the pair read as a pair. With identical labels-widths and identical values, the two lines align character for character, and a mismatch between what is being seen and what is being heard becomes visible instantly without reading a single word. That alignment IS the feature. Any decoration that breaks it (brackets, a colour on one row, an extra adjective) destroys the comparison.

**Colour rule, generalised:** on this dashboard, white means normal and colour means attention. The audio row turns red and shows the violation text only when the guard flags a stop; the video row turns red only when the captured window is blacklisted. No green anywhere in the card body. This should be written down, not just implemented, because it is the rule the current green "safe" broke.

**Also:** capture the dashboard's design principles in a `docs/DESIGN.md` (David: "docs design MD maybe") so the next change does not relitigate them. Cover the card grouping by API source, the muted accent colours that must not compete with the top-level state indicator, the white-normal/colour-attention rule, the symmetric Video/Audio pairing and why alignment matters, and the self-contained-no-external-requests constraint.

## P0 - Blocking bugs

*(none currently - OBS window staleness fixed: heartbeat now verifies + reapplies.
Twitch-auth-silently-looks-like-"not found" and the 20-window add-game cap were
both fixed 2026-07-13, see HISTORY.md)*

## Robustness follow-ups (found during 2026-07-13 code review, not yet needed)

- **add-game window picker still can't search/filter** - raised the cap 20->40 as
  an immediate fix, but on a very busy desktop it could still truncate. If this
  ever bites, swap `questionary.select` for `questionary.autocomplete` (built-in
  fuzzy text filter) instead of raising the cap further.
- **Twitch token expiry has no proactive warning during normal daemon operation
  (raised in priority 2026-07-21 - real risk, not just polish)** - add-game now
  validates and warns up front (fixed), but `daemon.py`'s `start()` also calls
  `self.twitch.validate()` (line ~102) without checking the result or logging clearly
  if it fails. Worth a heartbeat-visible warning if the token goes stale mid-session,
  same pattern as the SABnzbd/OBS checks. **Why this matters now:** a stale token
  means the dynamic title/tag/emoji PATCH silently fails every game launch - the
  exact feature the 2026-07-18/21 viewer-growth work shipped - with zero visible
  signal today.

- **Eight games David plays are missing from `config.games` - user action needed, not a code bug (raised 2026-07-28)** -
  SSF2.exe, FortniteClient-Win64-Shipping.exe, DOOMEternalx64vk.exe, javaw.exe,
  OblivionRemastered-Win64-Shipping.exe, SkyrimTogether.exe, Overwatch.exe, and wwm.exe
  are not entries in `config.games`. They used to work only because the old wide audio
  allow-list tolerated any exe; under `audio.exclusive_mode` (now the default, see
  HISTORY.md) the audio guard only allows the exe of the currently-detected game, and none
  of these will ever be detected as the current game since they aren't in `config.games` at
  all - the video-capture side (window detection, category switch, title/tags) won't work
  for them either. Streaming any of these titles needs a proper `add-game` run per game
  (captures the Twitch category id and the OBS window string), not a code fix. Note:
  `javaw.exe` is generic Java, not a specific game (many unrelated Java apps share that
  process name) - worth deciding whether it should be added at all, and if so, whether a
  narrower identifier (window title match) is needed instead of the bare exe name.

- **`tests/test_daemon.py` failed intermittently on 2026-07-26, cause unidentified** -
  during an unrelated git-history rewrite the full suite came back with several
  failures confined to `test_daemon.py`. Re-running the file on its own later the
  same day passed cleanly three times in a row, and the full suite passed too, so
  the failures are not reproducible on demand and the specific test names were not
  captured before the run scrolled away. The history rewrite itself is ruled out as
  the cause: its diff touched only `.gitignore`. Most likely something in the
  environment at that moment - a real daemon process holding a port or lock file,
  or another session running tests concurrently against the same tree. **Next time
  this happens, save the pytest output before doing anything else.** If it recurs,
  the fix is probably to make the daemon tests bind an ephemeral port and use a
  test-scoped state directory rather than whatever shared resource they currently
  assume is free.

## Dashboard tab title/favicon - future (harder stuff, easy version shipped 2026-07-13)
Shipped: tab title shows a colored dot + game name (🟢/🔴/⚪/⚫), favicon recolors
to match state. See HISTORY.md. Harder follow-ups, not done:
- **Genuinely animated/blinking favicon on ISSUE** - alternate the favicon between
  the color and blank on an interval so it catches the eye even in a background
  tab, not just a static recolor. More code (an interval + two icon states) and
  a flicker/attention tradeoff to get right - worth it only if the static
  recolor turns out to not be noticeable enough in practice.
- **Browser notification on OK->ISSUE transition** - `Notification` API popup
  when the state flips to ISSUE, so David doesn't need the tab visible at all.
  Needs a permission prompt (one-time) and only fires reliably if the tab/OS
  allows background notifications - real but bigger lift than the visual cues.
- **Audio ping on ISSUE** - a short sound cue as a second channel besides visual,
  useful if the second monitor isn't always in view. Simple `Audio()` object,
  but needs a user gesture first (browser autoplay policy) so isn't zero-effort.

## P1 - AudioManager (next major feature - start after QOL batch is done)

## System tray (do after status heartbeat)

**Note (2026-07-17):** Clean shutdown is now covered by the dashboard's Quit
button (stop stream, resume SABnzbd, close process - see HISTORY.md). Tray's
remaining value is narrower still - just the pre-game bookend:

1. **Pre-game confirmation** - before launching a game, David can glance at the tray and know the daemon is active, without needing the browser dashboard tab open/visible.

Implementation:
- `pystray` + `Pillow` for tray icon
- **Dynamic icon** - tick (all OK) or cross (issue) visible in taskbar while alt-tabbed to Discord or elsewhere
- Icon ready: `assets/StreamPilotIconICO.ico` + `assets/StreamPilotIconPNG.png`
- Tray tooltip: current state (Streaming: Marvel Rivals / Idle)
- The tray icon covers pre-game; the browser dashboard covers in-game monitoring and shutdown. Both are needed.

**Note on full-screen coverage:** tray IS covered when game is fullscreen on primary monitor, and Windows may not show it on the secondary. This is expected - tray's job is pre-game and post-game, not in-game. The dashboard on second screen covers in-game.

## Robustness (golden path stability)

- **SABnzbd pre-flight check (top item here - real, reproduced friction)** - before
  pausing/resuming, verify SABnzbd is actually running. Check process list first; log a
  clear warning and skip if not found. Observed: starting SP with SABnzbd not running
  caused a ~13s hang before the connection error was logged (Max retries exceeded).
  Should fail fast with a clear "SABnzbd not running" message instead.
  *(OBS's equivalent is already shipped - `daemon.py::_ensure_obs_running()` checks the
  process list and auto-launches OBS if it's not running, waiting up to 30s for the
  WebSocket. `_ensure_steam_running()` does the same for Steam. Only SABnzbd lacks this.)*
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
- **OBS Game Capture window fix verification** - when SP says `OBS Window: REAPPLIED`, the setting may show as "fixed" in WebSocket responses but OBS UI still displays the old window. Need to reproduce and determine root cause: OBS UI lag vs genuine application failure vs SP verification gap. If genuine, may need deeper OBS source verification or longer settle time.

**Design note:** The heartbeat pattern (poll every 2s, correct inline, flag ISSUE) works for any correction where the target service's API is reachable. OBS process restart requires a different mechanism (process supervision) - deliberately deferred.

## Security

- **Full security review** - `config.json` stores OAuth token, OBS WebSocket password, and SABnzbd API key in plaintext. Review subprocess calls, WebSocket trust model, any network exposure. Assess risk level and hardening options (OS keychain, env vars).

## Stretch goals

- **Setup/config web UI** - replace the batch-script setup flow (config editing, add-game wizard) with a browser-based UI. NOTE: the live-status half of this idea shipped 2026-07-13 as the dashboard, now built into `run.bat` itself - see HISTORY.md; this item is now scoped to config/setup only, not live status.

## Docs overhaul

- Review all docs (README, CLAUDE.md, IDEAS.md, any setup guides) - consolidate, remove duplication, tighten language. No data loss. Reduce total doc surface area. Specific pain point: README's linear step format doesn't reflect how the program actually works - particularly SABnzbd integration, which isn't a sequential setup step but a background behaviour. Restructure around how the program behaves, not a setup checklist.
- Add inline icon to the README heading - same pattern as Sonarr's README (`<img>` tag next to the `#` heading). Icon assets are already in `assets/`.

## Desktop shortcut / setup polish (raised 2026-07-19, not urgent)

`scripts/setup/make-desktop-shortcut.ps1` (shipped 2026-07-19) is deliberately
minimal - just enough to clean duplicates and regenerate the one shortcut.
Future polish, do not implement yet:
- **`.bat` double-click wrapper** - `make-desktop-shortcut.bat` that calls
  `powershell -ExecutionPolicy Bypass -File make-desktop-shortcut.ps1`, so
  David doesn't need to remember the powershell invocation - same pattern as
  `scripts/setup/add-game.bat` wrapping other logic. Low effort, quality of
  life only.
- **Also drop a copy of the shortcut in the repo** (mirrors a setup pattern
  from the maintainer's private tooling, which keeps a versioned copy of a
  shortcut alongside the Desktop one) - makes it obvious the
  shortcut is reproducible/version-controllable rather than a one-off manual
  Desktop artifact. Not clearly needed for a single-shortcut single-target
  tool like StreamPilot; only worth doing if the Desktop copy ever goes
  missing/gets manually edited again.
- **Add-game wizard could offer to (re)run the shortcut maker** at the end of
  first-time setup, so a fresh `git clone` + config fill-in doesn't need a
  separate manual step to get the Desktop icon.
- **Auto-start with Windows task (see Medium priority below) could reuse this
  script's target resolution** (`run.bat` path lookup) instead of hardcoding
  a separate path if that item is ever implemented.

## Medium priority

- **Auto-start with Windows** - Task Scheduler entry to launch StreamPilot on login.
- **Windows toast notification for unknown game (confirmed NOT built, 2026-07-21)** - CLAUDE.md's Key Behaviour section wrongly described this as already shipped ("Unknown game: Windows toast notification") - there is no toast/notification code anywhere in `src/`; today an unrecognised process is just silently ignored. CLAUDE.md line corrected 2026-07-21. Still an open idea: surface a Windows toast when an unrecognised process is detected, so it can be added via the add-game wizard without switching windows.
- **Brainstorm session with Claude** - dedicated session to generate a wide list of improvement ideas for StreamPilot. Purely generative, no implementation. Run as a separate `/dev-session`.

## Low priority

- **SABnzbd per-game config for offline games** - in config, flag games that SHOULDN'T pause SAB. Only multiplayer games need SAB paused; offline/single-player games should leave it running. No offline games currently, but worth designing for.
