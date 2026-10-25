# StreamPilot security review (STP-31, 2026-10-25)

Read-only review, no code or behaviour changed. No secret value appears here; keys are named only. Line numbers are against `main` at d68f8bf.

## Threat model

Single user, single Windows PC, one local daemon plus a loopback dashboard. The realistic attackers are (1) a web page in David's browser, (2) other software running as David, (3) someone who gets the config file by accident (backup, screen share, repo), (4) other machines on the LAN. A stream viewer is not an attacker unless a secret reaches the screen or a shown log.

## Secrets inventory

| Key in `config/config.json` | Used at | Grants |
|---|---|---|
| `twitch.oauth_token`, `twitch.client_id` | `src/twitch_client.py:18,26,34` | Edit the channel title, tags, category as David |
| `obs.password` | `src/obs_client.py:40`, `src/daemon.py:40` | Full OBS control (start or stop stream, change sources) |
| `sabnzbd.api_key` | `src/sabnzbd_client.py:14,20` | Full SABnzbd control |

Loaded by `src/config.py` `load()` as plain JSON with no encryption layer.

## Risks

### R1. SABnzbd API key in the URL query string and possibly in log text
- File: `src/sabnzbd_client.py:18-21` (param `apikey`), and the `log.warning(f"SABnzbd {mode} failed: {e}")` line at line 26.
- Severity: Medium.
- Preconditions: SABnzbd unreachable or erroring, so `requests` raises an exception whose text often embeds the request URL including the query; the message goes to the log file (`src/streampilot.py:45` FileHandler under `data/logs/`). Anyone who reads or shares that log gets the key. Plain `http://` also means the key crosses the wire unencrypted if `sabnzbd.host` is not this PC. Not verified against a live failure (no live probe allowed).
- Options:
  1. Log only the exception class and `mode`, never `str(e)`, plus a regex scrub of `apikey=` in one shared helper (recommended, small, no behaviour change).
  2. Send the key as a header if SABnzbd supports that for these modes (unverified).
  3. A logging filter on the root logger that masks every configured secret value.

### R2. Plaintext secrets at rest, readable by any process running as David
- File: `config/config.json` (read in `src/config.py` `load()`), ignore rule `config/config.json*` in `.gitignore` (the glob covers `.bak` copies). Verified no `config.json` is tracked in git.
- Severity: Medium (the Twitch token and OBS password are the most valuable).
- Preconditions: malware or any script under David's account, a cloud-synced or backed-up folder, or an accidental screen share of the file. The ignore rule only defends against commits.
- Options:
  1. Keep the file, restrict it to David's account with `icacls` (inheritance removed) and warn at startup if other principals can read it (low cost, no change to how secrets are read).
  2. Environment variables overriding the config keys so the file holds placeholders; weak on Windows because same-user processes can read user env vars and children inherit them.
  3. Windows Credential Manager via `keyring`, with `config.json` holding a reference. Strongest at rest, but adds a dependency and changes setup and hot-reload loading.
- Recommended: option 1 now. Option 3 only if David wants protection from other same-user software. **David decides** on option 3.

### R3. Twitch OAuth token: scope, provenance, error-body logging
- File: `src/twitch_client.py:26` (Bearer header on every Helix call), `:30-40` (`validate` logs `resp.text` on failure), `src/streampilot.py:141` and `docs/SETUP.md` Step 4 (third-party token generator).
- Severity: Medium.
- Preconditions: a token minted by a third-party generator carries whatever scopes were requested there; a leaked token lets an attacker change the live title and category, and more if scopes are broad. A Twitch error body is logged verbatim.
- Options:
  1. Document the minimal scope (`channel:manage:broadcast`) in `docs/SETUP.md` and have `validate` warn when the validate response lists extra scopes (recommended).
  2. Replace the third-party generator with Twitch's own device-code flow using a registered client (first-party, revocable token). **David decides** (setup and product change).
  3. Log only the HTTP status, not `resp.text`.

### R4. OBS WebSocket: host is config-driven and sent the password hash handshake
- File: `src/obs_client.py:40` (`ReqClient(host, port, password)`), `config/config.example.json` `obs.host`.
- Severity: Low to Medium.
- Preconditions: obs-websocket uses unencrypted `ws://`. If `obs.host` is not loopback the control channel is on the network. On localhost the risk is other local software, which can also open the port.
- Options:
  1. Validate in `config._validate` that `obs.host` is loopback unless an explicit opt-in key is set (recommended).
  2. Accept and document that OBS must bind to localhost with a strong password.
  3. Rotate the OBS password to a long random value.

### R5. Dashboard POST surface: loopback-only and well guarded; one token protects stream-affecting actions
- File: `src/dashboard_server.py:34` (`BIND_HOST`), `:39` (`TOKEN = secrets.token_urlsafe(24)`), `:595` (token embedded in the served page), `:683-698` (`_guard`: Host, Origin or Referer, constant-time token compare), `:718-750` (`/__log`, `/quit`, `/sab_toggle`, `/restart_stream`), `:788-791` (`make_server` refuses non-loopback).
- Severity: Low.
- Preconditions: `GET /` hands the token to any local process that sends `Host: localhost:<port>`, so other same-user software can already call `/quit`, whose `end_stream` defaults to true (`:740`), ending a live stream. Remote web pages are blocked by the Host check (DNS rebinding), same-origin Origin check and absence of CORS headers. `/__log` writes capped, whitespace-collapsed text (`:613-623`), so log injection is bounded.
- Positives to keep: exactly three GET routes (no directory serving, so `config.json` is unreachable), `SO_EXCLUSIVEADDRUSE`, CSP, `nosniff`, `no-store`.
- Options:
  1. Accept (same-user software can already kill OBS or edit the config) and keep the rule in `DevContext.md` (recommended).
  2. Default `/quit` `end_stream` to false so a stray call never ends a live stream; a behaviour change, **David decides**.
  3. Require a second confirmation token for `end_stream: true`.

### R6. Subprocess and process control
- File: `src/daemon.py:104` and `:132` (`Popen([exe_path])` for OBS and Steam), `src/launcher.py:58,190-193` (argv lists), `:83-88` (`taskkill /F /PID` of the port owner), `src/build.py:23`, `src/capture.py:68`, `src/verify.py:42`.
- Severity: Low.
- Preconditions: no `shell=True` anywhere in `src/`, all calls use argv lists, so no shell injection. The only externally influenced inputs are `obs.exe_path` and `steam.exe_path` from `config.json`; anyone who can edit that file already has worse options (R2). `kill_port_owner` only targets the dashboard port holder.
- Options:
  1. Accept; optionally have `_validate` check `exe_path` ends in `.exe` and exists (recommended, tiny).
  2. Basename allow-list (`obs64.exe`, `steam.exe`); blocks custom installs, **David decides**.

### R7. Transport for SABnzbd and Twitch
- File: `src/sabnzbd_client.py:13` (`http://`), `src/twitch_client.py:9,33` (HTTPS, default certificate verification, no `verify=False` found).
- Severity: Low.
- Preconditions: plain HTTP to SABnzbd matters only when `sabnzbd.host` is a remote machine.
- Options: keep with a local host (recommended); or add an `https` setting for a remote SABnzbd, **David decides**.

### R8. Hot-reload trigger file
- File: `src/hot_reload.py:58` (`data/state/reload.trigger`), `os.execv` restart.
- Severity: Low.
- Preconditions: any same-user process that creates the trigger can force an in-place restart (the stream is adopted, not ended). The re-exec uses the same interpreter and script; the file content only selects "force". No command execution path found.
- Options: accept (recommended).

## Recommended hardening order

1. R1: keep `str(e)` and the apikey query out of logs (small code item; test with a fake exception containing an `apikey=` URL).
2. R2 option 1: lock the ACL on `config/config.json` and warn at startup when it is broader.
3. R3 options 1 and 3: document minimum Twitch scope, warn on extras, stop logging the raw error body.
4. R4 option 1: loopback-only OBS host check in `_validate`.
5. David decides: Credential Manager (R2.3), device-code OAuth (R3.2), `/quit` default (R5.2), exe allow-list (R6.2), remote SABnzbd HTTPS (R7).

Suggested backlog items for the orchestrator: R1, R2.1, R3.1 and 3.3, R4.1.

## Not checked

No live probe of OBS, SABnzbd, Twitch or the running dashboard (rules: no start or stop, no live stream). Whether SABnzbd accepts an API key header was not verified. Existing log files on disk were not read, so whether a key already sits in a log is unknown.
