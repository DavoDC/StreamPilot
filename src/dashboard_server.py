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

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs', 'status.json')
PORT = 8765
POLL_MS = 1000  # how often the page re-fetches status.json

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
    min-width: 220px;
  }
  .row { display: flex; justify-content: space-between; gap: 20px; padding: 6px 0; font-size: 14px; }
  .row .label { color: #6b7280; }
  .row .value { font-weight: 600; }
  #footer { font-size: 11px; color: #6b7280; }
</style>
</head>
<body>
  <div id="dot"></div>
  <div id="badge">OFFLINE</div>
  <div id="panel">
    <div class="row"><span class="label">Game</span><span class="value" id="game">-</span></div>
    <div class="row"><span class="label">Category</span><span class="value" id="category">-</span></div>
    <div class="row"><span class="label">SABnzbd</span><span class="value" id="sabnzbd">-</span></div>
  </div>
  <div id="footer">waiting for daemon...</div>
<script>
const COLORS = { OK: "#3fd67a", ISSUE: "#ff5d5d", IDLE: "#6b7280", OFFLINE: "#4b5563" };
const TITLE_DOTS = { OK: "🟢", ISSUE: "🔴", IDLE: "⚪", OFFLINE: "⚫" };
const STALE_MULT = 4, STALE_FLOOR = 8;

function setFavicon(color) {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>` +
              `<circle cx='16' cy='16' r='13' fill='${color}'/></svg>`;
  document.getElementById("favicon").href = "data:image/svg+xml," + encodeURIComponent(svg);
}

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

  const state = stale ? "OFFLINE" : (s.status || "IDLE");
  const color = COLORS[state] || "#f5a623";

  document.getElementById("badge").textContent = state;
  document.getElementById("badge").style.color = color;
  document.getElementById("dot").style.background = color;
  setFavicon(color);

  if (stale) {
    document.getElementById("game").textContent = "-";
    document.getElementById("category").textContent = "-";
    document.getElementById("sabnzbd").textContent = "-";
    document.getElementById("footer").textContent = "No signal from daemon - is it running?";
    document.title = `${TITLE_DOTS[state]} Offline - StreamPilot`;
  } else {
    const game = s.game || "Idle";
    document.getElementById("game").textContent = game;
    document.getElementById("category").textContent = s.category || "Unknown";
    document.getElementById("sabnzbd").textContent = s.sabnzbd || "-";
    document.getElementById("footer").textContent =
      `updated ${Math.max(0, Math.round(age))}s ago  |  polling every ${s.poll_interval}s`;
    document.title = `${TITLE_DOTS[state]} ${game} - StreamPilot`;
  }
}
tick();
setInterval(tick, __POLL_MS__);
</script>
</body>
</html>
""".replace("__POLL_MS__", str(POLL_MS))


def status_json_bytes(status_path=STATUS_PATH) -> bytes:
    """Return the current status as JSON bytes, or an OFFLINE-shaped default
    if the daemon hasn't written anything yet."""
    data = status_file.read_status(status_path)
    if data is None:
        data = {"timestamp": 0, "status": "IDLE", "game": None, "category": None, "sabnzbd": None, "poll_interval": 2}
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


def run(port: int = PORT, open_browser: bool = True):
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
