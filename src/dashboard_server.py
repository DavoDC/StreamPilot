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
import os
import threading
import time
import webbrowser

import status_file

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'status.json')
PORT = 8765
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
     obvious - see docs/IDEAS.md "Dashboard grouped by API source". The
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
  .row .value { font-weight: 600; text-align: right; word-break: break-word; }
  /* De-emphasised exe suffix on the "Game Captured" row (e.g. "Palworld
     (Palworld-Win64-Shipping.exe)") - dimmer + smaller than the title so it
     reads as supporting detail, not a second headline, matching the .tag
     treatment used elsewhere for secondary text. */
  .row .value .exeSuffix { font-weight: 400; font-size: 12px; color: #6b7280; }
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

  #quitBtn {
    margin-top: 2px;
    background: none; border: 1px solid #262b34; border-radius: 6px;
    color: #565e6b; font-size: 12px; padding: 5px 14px;
    cursor: pointer; transition: border-color 0.2s ease, color 0.2s ease;
  }
  #quitBtn:hover, #quitBtn:focus-visible { border-color: #4b5563; color: #9ca3af; }

  .overlay {
    position: fixed; inset: 0; background: rgba(10, 12, 15, 0.6);
    display: flex; align-items: center; justify-content: center;
  }
  .overlay[hidden] { display: none; }

  #quitDialog {
    background: #1a1e26; border: 1px solid #262b34; border-radius: 10px;
    padding: 22px 24px; max-width: 320px; text-align: left;
  }
  #quitDialog:focus { outline: none; }
  #quitTitle { font-size: 16px; font-weight: 700; color: #e5e7eb; margin-bottom: 8px; }
  #quitDesc { font-size: 13px; color: #9ca3af; line-height: 1.5; }
  .quitActions { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; }
  .quitActions button {
    font-size: 13px; padding: 8px 16px; border-radius: 6px; cursor: pointer;
    border: 1px solid #2a2f38; background: #12151a; color: #c9d1d9; text-align: center;
  }
  #quitCancel:hover, #quitCancel:focus-visible { border-color: #4b5563; }
  #quitKeepStream { border-color: #1f3a52; color: #7cc4ff; }
  #quitKeepStream:hover, #quitKeepStream:focus-visible { background: #12212e; border-color: #3fa1ff; color: #a9d8ff; }
  #quitEndStream { background: #3a1418; border-color: #6b2530; color: #ff8787; }
  #quitEndStream:hover, #quitEndStream:focus-visible { background: #4a1a20; border-color: #ff5d5d; color: #ffb3b3; }
  .quitActions button:disabled { opacity: 0.5; cursor: default; }
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
      <div class="row"><span class="label">Game Captured</span><span class="value" id="capturedWindow">-</span></div>
      <div class="row" id="audioRow"><span class="label">Audio</span><span class="value" id="audio">-</span></div>
    </div>
    <div class="card card-twitch">
      <div class="card-header">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11a8 8 0 0 1 16 0"/><path d="M8 13a4 4 0 0 1 8 0"/><circle cx="12" cy="17" r="1.4" fill="currentColor" stroke="none"/></svg>
        Twitch
      </div>
      <div class="row"><span class="label">Category</span><span class="value" id="category">-</span></div>
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
      <div class="row"><span class="label">Keep SAB paused</span><span class="value"><label class="switch"><input type="checkbox" id="sabToggle" checked><span class="slider"></span></label></span></div>
    </div>
  </div>
  <div id="footer">waiting for daemon...</div>
  <button id="quitBtn" type="button">Quit</button>

  <div id="quitOverlay" class="overlay" hidden>
    <div id="quitDialog" role="alertdialog" aria-modal="true" aria-labelledby="quitTitle" aria-describedby="quitDesc" tabindex="-1">
      <div id="quitTitle">Quit StreamPilot?</div>
      <div id="quitDesc">Choose what happens to your stream.</div>
      <div class="quitActions">
        <button id="quitCancel" type="button">Cancel</button>
        <button id="quitKeepStream" type="button">Keep streaming</button>
        <button id="quitEndStream" type="button">End stream</button>
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

function setCapturedWindow(active, title, exe, gameName) {
  // Mirrors the Audio row's "safe (exe)" format so David can confirm video
  // and audio come from the SAME source at a glance - the title falls back
  // to the configured game name (as before), the exe is independent and
  // only shown (dimmer, smaller) when OBS's window string actually had one.
  // Never render an empty "()" - the exe span is only added when present.
  const el = document.getElementById("capturedWindow");
  if (!active) {
    el.textContent = "-";
    return;
  }
  const mainText = title || gameName;
  el.textContent = "";
  el.appendChild(document.createTextNode(mainText));
  if (exe) {
    const exeSpan = document.createElement("span");
    exeSpan.className = "exeSuffix";
    exeSpan.textContent = ` (${exe})`;
    el.appendChild(exeSpan);
  }
}

function setAudioRow(audioOk, violations, exes) {
  const el = document.getElementById("audio");
  if (audioOk === null || audioOk === undefined) {
    el.textContent = "-";
    el.style.color = "";
    return;
  }
  if (audioOk) {
    // Name the exe(s) audio is actually coming from, not just "safe" - under
    // exclusive mode this is normally one entry, so it's verifiable at a
    // glance instead of a bare verdict you have to trust blindly.
    const names = (exes || []).join(", ");
    el.textContent = names ? `safe (${names})` : "safe";
    el.style.color = "#3fd67a";
  } else {
    const messages = (violations || []).join("; ");
    el.textContent = messages ? `UNSAFE: ${messages}` : "UNSAFE";
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
let sabToggleDesired = null;
sabToggle.addEventListener("change", () => {
  sabToggleDesired = sabToggle.checked;
  fetch("/sab_toggle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: sabToggle.checked }),
  }).catch(() => {});
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
    setCapturedWindow(false, null, null, null);
    document.getElementById("category").textContent = "-";
    document.getElementById("title").textContent = "-";
    renderTags(null);
    document.getElementById("sabnzbd").textContent = "-";
    setAudioRow(null, null, null);
    sabToggle.disabled = true;
    document.getElementById("footer").textContent = "No signal from daemon - is it running?";
    document.title = `${TITLE_DOTS[state]} Offline - StreamPilot`;
  } else {
    const game = s.game || "Idle";
    // Actual captured WINDOW TITLE, not the configured game name (that
    // duplicated Category) - falls back to the game name if OBS's window
    // string is missing/malformed, and to "-" entirely when idle. The exe
    // suffix is independent of the title fallback (see setCapturedWindow).
    setCapturedWindow(!!s.game, s.captured_window_title, s.captured_window_exe, game);
    document.getElementById("category").textContent = s.category || "Unknown";
    document.getElementById("title").textContent = s.title || "-";
    renderTags(s.tags);
    document.getElementById("sabnzbd").textContent = s.sabnzbd || "-";
    setAudioRow(s.game ? s.audio_ok : null, s.audio_violations, s.audio_exes);
    sabToggle.disabled = false;
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
  fetch("/quit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ end_stream: endStream }),
  }).catch(() => {});
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
    html = INDEX_HTML.replace("__TWITCH_LINK_HTML__", _twitch_link_html(_twitch_channel))
    return html.encode("utf-8")


def status_json_bytes(status_path=STATUS_PATH) -> bytes:
    """Return the current status as JSON bytes, or an OFFLINE-shaped default
    if the daemon hasn't written anything yet."""
    data = status_file.read_status(status_path)
    if data is None:
        data = {"timestamp": 0, "status": "IDLE", "game": None, "category": None, "title": None, "tags": None, "sabnzbd": None, "poll_interval": 2, "build_id": None, "audio_ok": None, "audio_violations": None, "captured_window_title": None, "captured_window_exe": None, "audio_exes": None}
    return json.dumps(data).encode("utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; this is a status page, not a debug tool

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = index_html_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/status.json":
            body = status_json_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
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
            body = b'{"ok": true}'
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
            body = b'{"ok": true}'
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


def run(port: int = PORT, open_browser: bool = True, on_quit=None, twitch_channel: str = None, on_sab_toggle=None):
    global _on_quit_callback, _twitch_channel, _on_sab_toggle_callback
    _on_quit_callback = on_quit
    _twitch_channel = twitch_channel
    _on_sab_toggle_callback = on_sab_toggle
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
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
