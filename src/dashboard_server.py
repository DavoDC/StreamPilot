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
  #panel {
    background: #1a1e26; border-radius: 10px; padding: 14px 20px;
    min-width: 220px; max-width: 340px;
  }
  .row { display: flex; justify-content: space-between; gap: 20px; padding: 6px 0; font-size: 14px; }
  .row .label { color: #6b7280; flex-shrink: 0; }
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
  <div id="panel">
    <div class="row"><span class="label">Game</span><span class="value" id="game">-</span></div>
    <div class="row"><span class="label">Category</span><span class="value" id="category">-</span></div>
    <div class="row"><span class="label">Title</span><span class="value" id="title">-</span></div>
    <div class="row" id="tagsRow"><span class="label">Tags</span><span class="value" id="tags"></span></div>
    <div class="row"><span class="label">SABnzbd</span><span class="value" id="sabnzbd">-</span></div>
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

let lastBuildId = null;  // tracks the running process - see hot_reload.py

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
    document.getElementById("game").textContent = "-";
    document.getElementById("category").textContent = "-";
    document.getElementById("title").textContent = "-";
    renderTags(null);
    document.getElementById("sabnzbd").textContent = "-";
    document.getElementById("footer").textContent = "No signal from daemon - is it running?";
    document.title = `${TITLE_DOTS[state]} Offline - StreamPilot`;
  } else {
    const game = s.game || "Idle";
    document.getElementById("game").textContent = game;
    document.getElementById("category").textContent = s.category || "Unknown";
    document.getElementById("title").textContent = s.title || "-";
    renderTags(s.tags);
    document.getElementById("sabnzbd").textContent = s.sabnzbd || "-";
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


def status_json_bytes(status_path=STATUS_PATH) -> bytes:
    """Return the current status as JSON bytes, or an OFFLINE-shaped default
    if the daemon hasn't written anything yet."""
    data = status_file.read_status(status_path)
    if data is None:
        data = {"timestamp": 0, "status": "IDLE", "game": None, "category": None, "title": None, "tags": None, "sabnzbd": None, "poll_interval": 2, "build_id": None}
    return json.dumps(data).encode("utf-8")


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; this is a status page, not a debug tool

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = INDEX_HTML.encode("utf-8")
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
        else:
            self.send_error(404)


def run(port: int = PORT, open_browser: bool = True, on_quit=None):
    global _on_quit_callback
    _on_quit_callback = on_quit
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
