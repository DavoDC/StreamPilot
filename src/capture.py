"""Headless browser capture of every dashboard scenario (WS-093).

`python src/capture.py --fixture` serves each fixtures.SCENARIOS scenario on a spare port (port 0, never 8765) and
visits it with headless Chrome or Edge. For each it writes <scenario>.png and <scenario>.dom.html under
data/captures/dashboard-fixture/ (gitignored) and FAILS when the console logged an [app-error], the error banner is
visible, the build line or the FIXTURE banner is missing, a button lacks a data-testid, or the page does not paint
what the fixture's status says (ui_check). `--url http://localhost:8765` visits a running server read-only (no clicks,
live data: the screenshot is for looking at, only the page-health checks apply).
Exit 0 all pass, 1 a scenario failed, 2 could not run.
"""
import argparse
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
import ui_check  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BROWSER_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)
WINDOW = "520,1100"
BUILD_RE = re.compile(r'data-testid="build"[^>]*>\s*StreamPilot\s+\S+\s+\S+')


def find_chrome() -> Optional[str]:
    return next((c for c in BROWSER_CANDIDATES if Path(c).exists()), None)


def verify_dom(dom: str, console: str, fixture: bool = True) -> List[str]:
    """Page-health problems in one rendered page (empty list means it passes)."""
    problems = []
    if "[app-error]" in console:
        problems.append("console logged an [app-error]: " + next((l.strip() for l in console.splitlines() if "[app-error]" in l), ""))
    banner = re.search(r'<[a-z]+[^>]*id="error-banner"[^>]*>', dom)
    if not banner:
        problems.append("no error banner element in the page (page did not load)")
    elif not re.search(r"\bhidden\b", banner.group(0)):
        problems.append("error banner is visible: " + (ui_check.element_text(dom, "error-banner") or "?"))
    if dom and not BUILD_RE.search(dom):
        problems.append("footer has no build line")
    if fixture and dom and 'data-testid="fixture-banner"' not in dom:
        problems.append("fixture mode shows no FIXTURE banner")
    markup = re.sub(r"<(?:style|script)\b.*?</(?:style|script)>", "", dom, flags=re.S)  # CSS comments and JS strings are not buttons
    for tag in re.findall(r"<button(?:\s[^>]*)?>", markup):
        if "data-testid=" not in tag:
            problems.append("a button has no data-testid: " + tag[:60])
    return problems


def run_chrome(chrome: str, url: str, png: Path, timeout: float = 90.0):
    """(dom, console) from one headless visit; also writes the screenshot. Virtual time lets the page poll once."""
    profile = tempfile.mkdtemp(prefix="sp-capture-profile-")
    args = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
            f"--window-size={WINDOW}", "--hide-scrollbars", "--virtual-time-budget=4000", "--enable-logging=stderr",
            "--v=0", f"--screenshot={png}", "--dump-dom", url]
    done = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.stdout.decode("utf-8", errors="replace"), done.stderr.decode("utf-8", errors="replace")


def serve_scenario(name: str):
    """Serve one fixture scenario on a spare port; returns (base_url, stop)."""
    import dashboard_server
    dashboard_server.set_fixture(name)
    server = dashboard_server.make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def stop():
        server.shutdown()
        server.server_close()
        dashboard_server.set_fixture(None)
    return f"http://localhost:{server.server_address[1]}", stop


def capture(outdir: Path, chrome: str, scenarios: Optional[List[str]] = None, visit: Callable = None,
            serve: Callable = serve_scenario) -> dict:
    """Visit every scenario; returns {scenario: [problems]} and writes the artefacts."""
    visit = visit or run_chrome
    outdir.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in scenarios or list(fixtures.SCENARIOS):
        base, stop = serve(name)
        try:
            png = outdir / f"{name}.png"
            now = time.time()
            dom, console = visit(chrome, f"{base}/?scenario={name}", png)
            (outdir / f"{name}.dom.html").write_text(dom, encoding="utf-8")
            problems = verify_dom(dom, console) + (ui_check.check_dom(fixtures.status(name, now), dom, now) if dom else [])
            if not png.exists() or png.stat().st_size == 0:
                problems.append("no screenshot was written")
            results[name] = problems
        finally:
            stop()
    return results


def capture_url(base: str, outdir: Path, chrome: str, visit: Callable = None) -> dict:
    """Read-only visit of a running server: page-health checks only (the data is live, not a fixture)."""
    visit = visit or run_chrome
    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / "live.png"
    dom, console = visit(chrome, base.rstrip("/") + "/", png)
    (outdir / "live.dom.html").write_text(dom, encoding="utf-8")
    problems = verify_dom(dom, console, fixture=False)
    if not png.exists() or png.stat().st_size == 0:
        problems.append("no screenshot was written")
    return {"live": problems}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Headless capture of the dashboard; exit 0 all pass, 1 a scenario failed, 2 could not run.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", action="store_true", help="serve each fixture scenario on a spare port and capture it")
    mode.add_argument("--url", help="capture an already running dashboard, e.g. http://localhost:8765 (read-only)")
    ap.add_argument("--scenario", choices=list(fixtures.SCENARIOS), help="with --fixture, only this scenario")
    ap.add_argument("--out", help="output folder (default data/captures/dashboard-<fixture|live>)")
    args = ap.parse_args(argv)
    chrome = find_chrome()
    if not chrome:
        print("Could not run: Chrome or Edge was not found in the standard install folders.")
        return 2
    out = Path(args.out).resolve() if args.out else ROOT / "data" / "captures" / ("dashboard-fixture" if args.fixture else "dashboard-live")
    started = time.monotonic()
    try:
        results = (capture(out, chrome, [args.scenario] if args.scenario else None) if args.fixture
                   else capture_url(args.url, out, chrome))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not run: {exc}")
        return 2
    failed = {k: v for k, v in results.items() if v}
    for name, problems in results.items():
        print(f"  {'FAIL' if problems else 'ok  '} {name}" + "".join(f"\n       - {p}" for p in problems))
    print(f"Captured {len(results)} page(s) to {out} in {time.monotonic() - started:.1f}s: " + ("FAIL" if failed else "PASS"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
