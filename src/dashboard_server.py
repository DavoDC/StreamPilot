"""StreamPilot Dashboard - a very simple local web page for the second monitor.

Replaces "glance at the terminal spam" with a sleek browser tab: a big
OK/ISSUE/IDLE/OFFLINE badge and a live-pulsing heartbeat dot that proves the
page is alive, updated by polling status.json. Stdlib only (http.server) -
no Flask/FastAPI, no Node, no build step, one file.

SECURITY NOTE: this handler serves exactly two routes (the page, and the
status JSON) rather than the directory tree - config.json (OAuth token, OBS
password, SABnzbd API key) must never be reachable through this server, even
on localhost. Do not switch this to SimpleHTTPRequestHandler.
"""

import http.server
import json
import hmac
import os
import secrets
import socket
import threading
import time
import webbrowser
from urllib.parse import urlsplit

import build
import status_file

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'status.json')
PORT = 8765
BIND_HOST = "127.0.0.1"  # loopback only (WS-020); never all interfaces

# Per-launch secret embedded in the served page and required on every POST
# (WS-022). A page on another origin cannot read it (no CORS), so it cannot
# forge a state-changing request even if the browser sends one.
TOKEN = secrets.token_urlsafe(24)
TOKEN_HEADER = "X-StreamPilot-Token"
_ALLOWED_HOSTNAMES = ("localhost", "127.0.0.1")

SECURITY_HEADERS = (
    ("Cache-Control", "no-store"),
    ("X-Content-Type-Options", "nosniff"),
    ("Content-Security-Policy",
     "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
     "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
)
POLL_MS = 1000  # how often the page re-fetches status.json

# Set by run() before the server starts; called from the request-handling
# thread when the dashboard's Quit button is confirmed. Module-level (not a
# Handler field) because ThreadingHTTPServer instantiates a fresh Handler per
# request - there's nowhere else to stash it without a custom server class.
_on_quit_callback = None

# Same reasoning - set by run(), read by index_html_bytes() per request.
_twitch_channel = None

# Same pattern as _on_quit_callback - set by run(), called from the request
# thread when the dashboard's SAB auto-pause toggle is flipped.
_on_sab_toggle_callback = None

# Same pattern as _on_quit_callback - set by run(), called from the request
# thread when the dashboard's Restart Stream button is confirmed.
_on_restart_stream_callback = None

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>StreamPilot</title>
<link rel="icon" id="favicon" type="image/svg+xml" href="">
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; height: 100vh; display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 14px;
    background: #12151a; color: #c9d1d9;
    font-family: "Segoe UI", system-ui, sans-serif;
  }
  /* Browsers do NOT make form controls inherit the page font by default -
     without this, every <button>/<input> renders in the OS UI font instead
     of matching surrounding text (see docs/DESIGN.md). Apply to any new
     interactive element instead of repeating font-family per-selector. */
  button, input { font-family: inherit; }
  #dot {
    width: 28px; height: 28px; border-radius: 50%;
    background: #4b5563; transition: background 0.3s ease;
    animation: pulse 1s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { transform: scale(0.75); }
    50% { transform: scale(1.15); }
  }
  #badge { font-size: 28px; font-weight: 700; letter-spacing: 1px; }
  /* One soft-edged, colour-coded card per API source (OBS / Twitch /
     SABnzbd) so related facts stay together and each fact's origin is
     obvious (see docs/DESIGN.md). The
     big OK/ISSUE badge above stays the primary state signal; card colours
     are deliberately muted (dark fill, a thin accent border only) so they
     never compete with it. */
  #cards {
    display: flex; flex-direction: column; gap: 12px;
    min-width: 220px; max-width: 340px; width: 100%;
  }
  .card {
    background: #1a1e26; border: 1px solid #262b34; border-left: 3px solid var(--accent);
    border-radius: 10px; padding: 12px 16px 14px;
  }
  .card-header {
    display: flex; align-items: center; gap: 7px;
    font-size: 11px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase;
    color: #8b93a1; margin-bottom: 6px;
  }
  .card-header svg { color: var(--accent); flex-shrink: 0; }
  .card-obs { --accent: #3fa1ff; }
  .card-twitch { --accent: #a970ff; }
  .card-sab { --accent: #f0a860; }
  .row { display: flex; justify-content: space-between; gap: 20px; padding: 6px 0; font-size: 14px; }
  .row .label { color: #6b7280; flex-shrink: 0; }
  /* Video and Audio share this class with identical font-size/weight/color
     (no per-row override) so the two values align character for character -
     that alignment is what makes a video/audio source mismatch visible
     without reading a word. See docs/DESIGN.md. Colour is only ever set
     inline (via JS, on a violation) - never in this base rule, which is
     what keeps white the default and colour reserved for attention. */
  .row .value { font-weight: 600; text-align: right; word-break: break-word; }
  #tagsRow { flex-direction: column; align-items: flex-start; gap: 6px; }
  #tagsRow .label { flex-shrink: unset; }
  #tags {
    display: flex; flex-wrap: wrap; gap: 6px; width: 100%;
  }
  #tags:empty::before, #tags.empty::before { content: "-"; font-weight: 600; color: #c9d1d9; }
  .tag {
    background: #262b34; color: #9ca3af; font-size: 11px; font-weight: 600;
    padding: 3px 9px; border-radius: 999px; line-height: 1.4;
  }
  #footer { font-size: 11px; color: #6b7280; }

  .switch { position: relative; display: inline-block; width: 34px; height: 20px; flex-shrink: 0; }
  .switch input { position: absolute; opacity: 0; width: 100%; height: 100%; margin: 0; cursor: pointer; }
  .switch .slider {
    position: absolute; inset: 0; background: #262b34; border-radius: 999px;
    transition: background 0.2s ease;
  }
  .switch .slider::before {
    content: ""; position: absolute; width: 14px; height: 14px; left: 3px; top: 3px;
    background: #6b7280; border-radius: 50%;
    transition: transform 0.2s ease, background 0.2s ease;
  }
  .switch input:checked + .slider { background: #1f3a52; }
  .switch input:checked + .slider::before { transform: translateX(14px); background: #3fa1ff; }
  .switch input:disabled { cursor: default; }
  .switch input:disabled + .slider { opacity: 0.5; }
  .switch input:focus-visible + .slider { outline: 2px solid #4b5563; outline-offset: 2px; }

  #twitchLink {
    display: inline-block; margin-top: 8px;
    color: #a970ff; font-size: 13px; font-weight: 600; text-decoration: none;
    padding: 6px 14px; border: 1px solid #3a2a5c; border-radius: 6px;
    transition: border-color 0.2s ease, color 0.2s ease;
  }
  #twitchLink:hover, #twitchLink:focus-visible { border-color: #a970ff; color: #c9a3ff; }

  #actions { display: flex; gap: 8px; margin-top: 2px; }
  /* Shared by Quit and Restart Stream so a new footer button never needs its
     own CSS block - just this class plus an optional accent modifier. */
  .footerBtn {
    background: none; border: 1px solid #262b34; border-radius: 6px;
    color: #565e6b; font-size: 12px; padding: 5px 14px;
    cursor: pointer; transition: border-color 0.2s ease, color 0.2s ease;
  }
  .footerBtn:hover, .footerBtn:focus-visible { border-color: #4b5563; color: #9ca3af; }
  .footerBtn:disabled { opacity: 0.5; cursor: default; }
  /* Restart Stream keeps the stream going (unlike End stream) - reuses the
     existing blue "keep streaming" accent rather than inventing a new hue. */
  .footerBtn.accent-blue:hover, .footerBtn.accent-blue:focus-visible { border-color: #3fa1ff; color: #a9d8ff; }

  .overlay {
    position: fixed; inset: 0; background: rgba(10, 12, 15, 0.6);
    display: flex; align-items: center; justify-content: center;
  }
  .overlay[hidden] { display: none; }

  /* Shared by the Quit and Restart Stream confirmation dialogs - reused by
     class rather than duplicated per-dialog CSS. IDs stay on the elements
     for aria-labelledby/aria-describedby and JS hooks. */
  .dialog {
    background: #1a1e26; border: 1px solid #262b34; border-radius: 10px;
    padding: 22px 24px; max-width: 320px; text-align: left;
  }
  .dialog:focus { outline: none; }
  .dialogTitle { font-size: 16px; font-weight: 700; color: #e5e7eb; margin-bottom: 8px; }
  .dialogDesc { font-size: 13px; color: #9ca3af; line-height: 1.5; }
  .dialogActions { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; }
  .dialogActions button {
    font-size: 13px; padding: 8px 16px; border-radius: 6px; cursor: pointer;
    border: 1px solid #2a2f38; background: #12151a; color: #c9d1d9; text-align: center;
  }
  #quitCancel:hover, #quitCancel:focus-visible,
  #restartCancel:hover, #restartCancel:focus-visible { border-color: #4b5563; }
  #quitKeepStream, #restartConfirm { border-color: #1f3a52; color: #7cc4ff; }
  #quitKeepStream:hover, #quitKeepStream:focus-visible,
  #restartConfirm:hover, #restartConfirm:focus-visible { background: #12212e; border-color: #3fa1ff; color: #a9d8ff; }
  #quitEndStream { background: #3a1418; border-color: #6b2530; color: #ff8787; }
  #quitEndStream:hover, #quitEndStream:focus-visible { background: #4a1a20; border-color: #ff5d5d; color: #ffb3b3; }
  .dialogActions button:disabled { opacity: 0.5; cursor: default; }
</style>
</head>
<body>
  <div id="dot"></div>
  <div id="badge">OFFLINE</div>
  <div id="cards">
    <div class="card card-obs">
      <div class="card-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="6" width="14" height="12" rx="2"/><path d="M16 10l6-4v12l-6-4"/></svg>
        OBS
      </div>
      <div class="row"><span class="label">Video</span><span class="value" id="video">-</span></div>
      <div class="row" id="audioRow"><span class="label">Audio</span><span class="value" id="audio">-</span></div>
    </div>
    <div class="card card-twitch">
      <div class="card-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a8 8 0 0 1 16 0"/><path d="M8 13a4 4 0 0 1 8 0"/><circle cx="12" cy="17" r="1.4" fill="currentColor" stroke="none"/></svg>
        Twitch
      </div>
      <div class="row"><span class="label">Category</span><span class="value" id="category">-</span></div>
      <div class="row"><span class="label">Live for</span><span class="value" id="uptime">-</span></div>
      <div class="row"><span class="label">Title</span><span class="value" id="title">-</span></div>
      <div class="row" id="tagsRow"><span class="label">Tags</span><span class="value" id="tags"></span></div>
      __TWITCH_LINK_HTML__
    </div>
    <div class="card card-sab">
      <div class="card-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v10"/><path d="M8 9l4 4 4-4"/><path d="M4 17h16v3H4z"/></svg>
        SABnzbd
      </div>
      <div class="row"><span class="label">Status</span><span class="value" id="sabnzbd">-</span></div>
      <div class="row"><span class="label">Activity</span><span class="value" id="sabActivity">-</span></div>
      <div class="row"><span class="label" title="ON: StreamPilot pauses SABnzbd when a game starts, re-pauses it if it drifts, and resumes it when the game exits. When no game is running (idle), SABnzbd runs freely. OFF: StreamPilot never touches SABnzbd (resumes it immediately).">Keep SAB paused while gaming</span><span class="value"><label class="switch"><input type="checkbox" id="sabToggle" checked><span class="slider"></span></label></span></div>
    </div>
  </div>
  <div id="footer">waiting for daemon...</div>
  <div id="actions">
    <button id="restartBtn" class="footerBtn accent-blue" type="button">Restart Stream</button>
    <button id="quitBtn" class="footerBtn" type="button">Quit</button>
  </div>

  <div id="quitOverlay" class="overlay" hidden>
    <div id="quitDialog" class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="quitTitle" aria-describedby="quitDesc" tabindex="-1">
      <div id="quitTitle" class="dialogTitle">Quit StreamPilot?</div>
      <div id="quitDesc" class="dialogDesc">Choose what happens to your stream.</div>
      <div class="dialogActions">
        <button id="quitCancel" type="button">Cancel</button>
        <button id="quitKeepStream" type="button">Keep streaming</button>
        <button id="quitEndStream" type="button">End stream</button>
      </div>
    </div>
  </div>

  <div id="restartOverlay" class="overlay" hidden>
    <div id="restartDialog" class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="restartTitle" aria-describedby="restartDesc" tabindex="-1">
      <div id="restartTitle" class="dialogTitle">Restart Stream?</div>
      <div id="restartDesc" class="dialogDesc">Ends the current VOD and starts a new one for the same game. StreamPilot keeps running.</div>
      <div class="dialogActions">
        <button id="restartCancel" type="button">Cancel</button>
        <button id="restartConfirm" type="button">Restart Stream</button>
      </div>
    </div>
  </div>
<script>
const COLORS = { OK: "#3fd67a", ISSUE: "#ff5d5d", IDLE: "#6b7280", OFFLINE: "#4b5563" };
const TITLE_DOTS = { OK: "🟢", ISSUE: "🔴", IDLE: "⚪", OFFLINE: "⚫" };
const STALE_MULT = 4, STALE_FLOOR = 8;

function setFavicon(color) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>` +
              `<circle cx='16' cy='16' r='13' fill='${color}'/></svg>`;
  document.getElementById("favicon").href = "data:image/svg+xml," + encodeURIComponent(svg);
}

function formatUptime(startedAt) {
  // started_at is fixed for the life of a broadcast (see daemon.py) - elapsed
  // is computed client-side from it each tick, same approach already used
  // for the "updated Xs ago" footer, so no extra polling is needed.
  if (!startedAt) return "-";
  const start = Date.parse(startedAt);
  if (isNaN(start)) return "-";
  const secs = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m ${s}s`;
  return `${m}m ${s}s`;
}

function renderTags(tags) {
  const el = document.getElementById("tags");
  el.innerHTML = "";
  if (!tags || !tags.length) return;  // :empty CSS rule shows the "-" placeholder
  for (const tag of tags) {
    const chip = document.createElement("span");
    chip.className = "tag";
    chip.textContent = tag;
    el.appendChild(chip);
  }
}

function setVideoRow(active, exe, blacklistedWindow) {
  // Bare exe name only, plain white, identical formatting to the Audio row -
  // no window title, no brackets - so the two rows align character for
  // character and a mismatch is visible without reading either one. See
  // docs/DESIGN.md. Colour turns red only when the captured window is
  // blacklisted (something needs attention); otherwise no inline colour at
  // all, so it falls back to the row's plain white.
  const el = document.getElementById("video");
  if (!active) {
    el.textContent = "-";
    el.style.color = "";
    return;
  }
  el.textContent = exe || "-";
  el.style.color = blacklistedWindow ? "#ff5d5d" : "";
}

function setAudioRow(audioOk, violations, exes) {
  // Bare exe name(s) only when healthy - plain white, no prefix word, no
  // brackets - identical formatting to the Video row so the pair is
  // comparable at a glance (see docs/DESIGN.md). Colour turns red only on a
  // stop violation, showing the guard's own violation text.
  const el = document.getElementById("audio");
  if (audioOk === null || audioOk === undefined) {
    el.textContent = "-";
    el.style.color = "";
    return;
  }
  if (audioOk) {
    const names = (exes || []).join(", ");
    el.textContent = names || "-";
    el.style.color = "";
  } else {
    const messages = (violations || []).join("; ");
    el.textContent = messages || "UNSAFE";
    el.style.color = "#ff5d5d";
  }
}

let lastBuildId = null;  // tracks the running process - see hot_reload.py

const sabToggle = document.getElementById("sabToggle");
// Holds the value we just asked the daemon for. A poll in flight when the
// user clicks can still land afterwards carrying the OLD status.json value
// (the daemon writes it on its own heartbeat, not synchronously with the
// POST) - that stale poll would otherwise snap the switch back before the
// next poll (with the daemon's actual new state) snaps it forward again.
// Keeping this set until a poll's value matches what we asked for closes
// that window, instead of clearing it as soon as the POST round-trip ends.
// All state-changing requests carry the per-launch token (server rejects without it).
const SP_TOKEN = "__STREAMPILOT_TOKEN__";
function postAction(path, payload) {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-StreamPilot-Token": SP_TOKEN },
    body: JSON.stringify(payload),
  });
}
let sabToggleDesired = null;
sabToggle.addEventListener("change", () => {
  sabToggleDesired = sabToggle.checked;
  postAction("/sab_toggle", { enabled: sabToggle.checked }).catch(() => {});
});

async function tick() {
  let s = null;
  try {
    const res = await fetch("/status.json", { cache: "no-store" });
    s = await res.json();
  } catch (e) { /* server unreachable - treat as offline below */ }

  const now = Date.now() / 1000;
  const age = s ? now - s.timestamp : Infinity;
  const maxAge = s ? Math.max((s.poll_interval || 2) * STALE_MULT, STALE_FLOOR) : 0;
  const stale = !s || age > maxAge;

  // The server behind this tab restarted (code change via --watch, or a
  // manual restart) - reload so we pick up new HTML/CSS/JS immediately.
  if (!stale && s.build_id) {
    if (lastBuildId === null) {
      lastBuildId = s.build_id;
    } else if (s.build_id !== lastBuildId) {
      location.reload();
      return;
    }
  }

  const state = stale ? "OFFLINE" : (s.status || "IDLE");
  const color = COLORS[state] || "#f5a623";

  document.getElementById("badge").textContent = state;
  document.getElementById("badge").style.color = color;
  document.getElementById("dot").style.background = color;
  setFavicon(color);

  if (stale) {
    setVideoRow(false, null, null);
    document.getElementById("category").textContent = "-";
    document.getElementById("uptime").textContent = "-";
    document.getElementById("title").textContent = "-";
    renderTags(null);
    document.getElementById("sabnzbd").textContent = "-";
    document.getElementById("sabActivity").textContent = "-";
    setAudioRow(null, null, null);
    sabToggle.disabled = true;
    restartBtn.disabled = true;
    document.getElementById("footer").textContent = "No signal from daemon - is it running?";
    document.title = `${TITLE_DOTS[state]} Offline - StreamPilot`;
  } else {
    const game = s.game || "Idle";
    setVideoRow(!!s.game, s.captured_window_exe, s.blacklisted_window);
    document.getElementById("category").textContent = s.category || "Unknown";
    document.getElementById("uptime").textContent = formatUptime(s.stream_started_at);
    document.getElementById("title").textContent = s.title || "-";
    renderTags(s.tags);
    document.getElementById("sabnzbd").textContent = s.sab_status || s.sabnzbd || "-";
    document.getElementById("sabActivity").textContent = s.sab_activity || "-";
    setAudioRow(s.game ? s.audio_ok : null, s.audio_violations, s.audio_exes);
    sabToggle.disabled = false;
    // Only meaningful once a stream is actually live - nothing to restart
    // for an idle/not-yet-live game.
    restartBtn.disabled = !s.streaming;
    const daemonValue = s.sab_auto_manage !== undefined ? s.sab_auto_manage : true;
    if (sabToggleDesired !== null && daemonValue === sabToggleDesired) {
      sabToggleDesired = null;  // daemon caught up - resume following polls
    }
    if (sabToggleDesired === null) {
      sabToggle.checked = daemonValue;
    }
    document.getElementById("footer").textContent =
      `updated ${Math.max(0, Math.round(age))}s ago  |  polling every ${s.poll_interval}s`;
    document.title = `${TITLE_DOTS[state]} ${game} - StreamPilot`;
  }
}
tick();
setInterval(tick, __POLL_MS__);

const restartBtn = document.getElementById("restartBtn");
const quitBtn = document.getElementById("quitBtn");
const quitOverlay = document.getElementById("quitOverlay");
const quitDialog = document.getElementById("quitDialog");
const quitCancel = document.getElementById("quitCancel");
const quitKeepStream = document.getElementById("quitKeepStream");
const quitEndStream = document.getElementById("quitEndStream");
const quitDesc = document.getElementById("quitDesc");

function onQuitKeydown(e) {
  if (e.key === "Escape") closeQuitDialog();
}
function openQuitDialog() {
  quitOverlay.hidden = false;
  quitDialog.focus();
  document.addEventListener("keydown", onQuitKeydown);
}
function closeQuitDialog() {
  quitOverlay.hidden = true;
  document.removeEventListener("keydown", onQuitKeydown);
  quitBtn.focus();
}
function confirmQuit(endStream, inProgressMessage) {
  quitCancel.disabled = true;
  quitKeepStream.disabled = true;
  quitEndStream.disabled = true;
  quitDesc.textContent = inProgressMessage;
  postAction("/quit", { end_stream: endStream }).catch(() => {});
}

quitBtn.addEventListener("click", openQuitDialog);
quitCancel.addEventListener("click", closeQuitDialog);
quitOverlay.addEventListener("click", (e) => {
  if (e.target === quitOverlay) closeQuitDialog();
});
quitKeepStream.addEventListener("click", () => {
  confirmQuit(false, "Closing StreamPilot - your stream keeps running...");
});
quitEndStream.addEventListener("click", () => {
  confirmQuit(true, "Stopping the stream and closing StreamPilot...");
});

const restartOverlay = document.getElementById("restartOverlay");
const restartDialog = document.getElementById("restartDialog");
const restartCancel = document.getElementById("restartCancel");
const restartConfirm = document.getElementById("restartConfirm");

function onRestartKeydown(e) {
  if (e.key === "Escape") closeRestartDialog();
}
function openRestartDialog() {
  restartOverlay.hidden = false;
  restartDialog.focus();
  document.addEventListener("keydown", onRestartKeydown);
}
function closeRestartDialog() {
  restartOverlay.hidden = true;
  document.removeEventListener("keydown", onRestartKeydown);
  restartCancel.disabled = false;
  restartConfirm.disabled = false;
  restartBtn.focus();
}

restartBtn.addEventListener("click", openRestartDialog);
restartCancel.addEventListener("click", closeRestartDialog);
restartOverlay.addEventListener("click", (e) => {
  if (e.target === restartOverlay) closeRestartDialog();
});
restartConfirm.addEventListener("click", () => {
  restartCancel.disabled = true;
  restartConfirm.disabled = true;
  postAction("/restart_stream", {})
    .catch(() => {})
    .finally(closeRestartDialog);
});
</script>
</body>
</html>
""".replace("__POLL_MS__", str(POLL_MS))


def _twitch_link_html(channel: str | None) -> str:
    """Small "Watch on Twitch" link so David can jump straight to the live
    view without typing the URL - empty string (nothing rendered) if no
    channel is configured."""
    if not channel:
        return ""
    url = f"https://www.twitch.tv/{channel}"
    return f'<a id="twitchLink" href="{url}" target="_blank" rel="noopener noreferrer">Watch on Twitch ↗</a>'


def index_html_bytes() -> bytes:
    """Render INDEX_HTML with the current Twitch channel link substituted in."""
    html = INDEX_HTML.replace("__TWITCH_LINK_HTML__", _twitch_link_html(_twitch_channel)).replace("__STREAMPILOT_TOKEN__", TOKEN)
    return html.encode("utf-8")


def status_json_bytes(status_path=STATUS_PATH) -> bytes:
    """Return the current status as JSON bytes, or an OFFLINE-shaped default
    if the daemon hasn't written anything yet."""
    data = status_file.read_status(status_path)
    if data is None:
        data = {"timestamp": 0, "status": "IDLE", "game": None, "category": None, "title": None, "tags": None, "sabnzbd": None, "poll_interval": 2, "build_id": None, "audio_ok": None, "audio_violations": None, "captured_window_exe": None, "audio_exes": None, "blacklisted_window": None, "stream_started_at": None}
    return json.dumps(data).encode("utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; this is a status page, not a debug tool

    # --- guard (WS-021, WS-022) -------------------------------------------
    def _own_port(self) -> int:
        return self.server.server_address[1]

    def _origin_ok(self, value: str) -> bool:
        """True if value (an Origin or Referer URL) is this server's own origin."""
        try:
            u = urlsplit(value)
            return (u.scheme == "http" and u.hostname in _ALLOWED_HOSTNAMES
                    and u.port == self._own_port())
        except ValueError:
            return False

    def _host_ok(self) -> bool:
        try:
            u = urlsplit("//" + self.headers.get("Host", ""))
            return u.hostname in _ALLOWED_HOSTNAMES and u.port == self._own_port()
        except ValueError:
            return False

    def _send(self, status: int, ctype: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in SECURITY_HEADERS:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _deny(self, why: str) -> None:
        self._send(403, "application/json", json.dumps({"ok": False, "error": why}).encode("utf-8"))

    def _guard(self, state_changing: bool) -> bool:
        """Return True if the request may proceed; otherwise a 403 was sent."""
        if not self._host_ok():
            self._deny("bad host")
            return False
        if state_changing:
            origin = self.headers.get("Origin")
            source = origin if origin is not None else self.headers.get("Referer")
            if source is None or not self._origin_ok(source):
                self._deny("bad origin")
                return False
            sent = self.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(sent.encode("utf-8"), TOKEN.encode("utf-8")):
                self._deny("bad token")
                return False
        return True

    def do_OPTIONS(self):
        # No CORS: preflights get the Host guard, then a plain 405.
        if self._guard(False):
            self.send_error(405)

    def do_GET(self):
        if not self._guard(False):
            return
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", index_html_bytes())
        elif self.path == "/status.json":
            self._send(200, "application/json", status_json_bytes())
        elif self.path == "/api/build":
            self._send(200, "application/json", json.dumps(build.info()).encode("utf-8"))
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._guard(True):
            return
        if self.path == "/quit":
            end_stream = True
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                    end_stream = bool(payload.get("end_stream", True))
                except (json.JSONDecodeError, ValueError):
                    pass
            if _on_quit_callback:
                _on_quit_callback(end_stream=end_stream)
            self._send(202, "application/json", b'{"ok": true}')
        elif self.path == "/sab_toggle":
            length = int(self.headers.get("Content-Length", 0) or 0)
            enabled = None
            if length:
                try:
                    payload = json.loads(self.rfile.read(length))
                    enabled = payload.get("enabled")
                except (json.JSONDecodeError, ValueError):
                    pass
            if not isinstance(enabled, bool):
                self.send_error(400, "Missing or invalid 'enabled' boolean")
                return
            if _on_sab_toggle_callback:
                _on_sab_toggle_callback(enabled=enabled)
            self._send(202, "application/json", b'{"ok": true}')
        elif self.path == "/restart_stream":
            if _on_restart_stream_callback:
                _on_restart_stream_callback()
            self._send(202, "application/json", b'{"ok": true}')
        else:
            self.send_error(404)


class ExclusiveServer(http.server.ThreadingHTTPServer):
    """On Windows SO_REUSEADDR lets a second process bind a port another is
    already listening on, so a stale dashboard keeps answering. Bind exclusively."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(port: int = PORT, host: str = BIND_HOST) -> http.server.ThreadingHTTPServer:
    """Create the dashboard server. Refuses any non-loopback host (WS-020)."""
    if host != BIND_HOST:
        raise ValueError(f"dashboard must bind {BIND_HOST} only, got {host!r}")
    return ExclusiveServer((host, port), Handler)


def bind_with_retry(port: int, attempts: int = 50, delay: float = 0.2, sleep=time.sleep):
    """Bind, retrying briefly: after an os.execv hot reload the old socket can
    linger for a moment (WS-006). Raises the last OSError when it never frees."""
    for i in range(attempts):
        try:
            return make_server(port)
        except OSError:
            if i == attempts - 1:
                raise
            sleep(delay)


def run(port: int = PORT, open_browser: bool = True, on_quit=None, twitch_channel: str = None, on_sab_toggle=None, on_restart_stream=None):
    global _on_quit_callback, _twitch_channel, _on_sab_toggle_callback, _on_restart_stream_callback
    _on_quit_callback = on_quit
    _twitch_channel = twitch_channel
    _on_sab_toggle_callback = on_sab_toggle
    _on_restart_stream_callback = on_restart_stream
    server = bind_with_retry(port)
    port = server.server_address[1]
    url = f"http://localhost:{port}/"
    print(f"[StreamPilot Dashboard] Serving at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    run()
