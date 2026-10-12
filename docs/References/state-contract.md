# /status.json state contract

`GET /status.json` on the dashboard server is the one machine-readable view of StreamPilot. The page, the tray icon, the fixture scenarios and the capture all read this shape. The daemon writes it to `data/state/status.json` each heartbeat (`src/status_file.py`); the server adds the three contract fields below on every read. Never edit the file by hand.

## Contract fields (added by the server)

| Field | Type | Meaning |
|---|---|---|
| `schema` | int | Contract version (`STATUS_SCHEMA`, currently 1). Bump it when a field is renamed, removed or changes meaning. Adding a field does not bump it. |
| `generated_at` | float | Unix time the server built this response. |
| `stale` | bool | True when the verdict is OFFLINE: no fresh daemon write within `max(poll_interval * 4, 8)` seconds (`status_file.STALE_MULTIPLIER`, `STALE_FLOOR_SECONDS`). A stale file never reads as healthy. |

## Daemon fields

| Field | Type | Meaning |
|---|---|---|
| `timestamp` | float | Unix time of the daemon's last write. |
| `status` | string | `OK`, `ISSUE`, `IDLE` as the daemon sees it. The page shows OFFLINE instead when `stale` is true. |
| `game` | string or null | Detected game, if any. |
| `streaming` | bool | OBS is streaming. |
| `category` | string or null | Twitch category set. |
| `title` | string or null | Twitch title. Can be long; the page wraps it. |
| `tags` | list or null | Twitch tags. |
| `sabnzbd` | string or null | SABnzbd state text (`Running`, `Paused (auto)`, ...). |
| `sab_auto_manage` | bool | Keep SAB paused while gaming is on. |
| `poll_interval` | number | Seconds between daemon polls; drives the stale window. |
| `build_id` | string or null | Daemon boot id; the page reloads itself when it changes. |
| `obs_window_ok` | bool or null | The captured OBS window is a game window. |
| `blacklisted_window` | string or null | A blocked window being captured, if any. |
| `stream_restarted` | bool | The stream was restarted by the safety guard. |
| `audio_ok` | bool or null | Audio capture passes the privacy guard. |
| `audio_violations` | list or null | Guard messages when audio is unsafe. |
| `captured_window_exe` | string or null | Executable OBS is capturing. |
| `audio_exes` | list or null | Executables whose audio is captured. |
| `stream_started_at` | ISO 8601 string or null | UTC start time, used for "Live for". |

## Verdict

`src/health.py` `verdict()` turns this into one of OK, ISSUE, IDLE, OFFLINE for the badge, the tray colour and `stale`. Do not recompute it elsewhere.

## Fixtures

`src/fixtures.py` holds the scenarios (idle, live, issue, offline, stale, long-title) in exactly this shape. `python src/streampilot.py fixture --scenario issue` serves one on a spare port; `python src/capture.py --fixture` captures all of them and runs the DOM checks.
