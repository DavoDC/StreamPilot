"""Does the rendered page show what /status.json says? (WS-093)

`check_dom(status, dom)` compares a dumped page against the status dict it was served and returns the problems
(an empty list is a pass). It re-derives each expected value from the status through the same rules the page uses,
so a render bug (wrong badge, a lost audio violation, dropped tags, a stale page still showing live rows) fails here
instead of being noticed on the second monitor mid-stream.
"""

import html
import re
from typing import List

import health


def element_text(dom: str, testid: str):
    """Plain text of the element carrying data-testid, or None when it is absent."""
    m = re.search(r'data-testid="%s"[^>]*>(.*?)</(?:span|div|button)>' % re.escape(testid), dom, re.S)
    return None if not m else html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()


def expected(status, now=None) -> dict:
    """The text each row should show for a status dict (mirrors the page's tick())."""
    state = health.verdict(status, now)
    stale = state == "OFFLINE"
    game = None if stale else status.get("game")
    audio = "-"
    if game and status.get("audio_ok") is not None:
        if status["audio_ok"]:
            audio = ", ".join(status.get("audio_exes") or []) or "-"
        else:
            audio = "; ".join(status.get("audio_violations") or []) or "UNSAFE"
    return {
        "badge": state,
        "video": (status.get("captured_window_exe") or "-") if game else "-",
        "audio": audio,
        "category": "-" if stale else (status.get("category") or "Unknown"),
        "title": "-" if stale else (status.get("title") or "-"),
        "tags": 0 if stale else len(status.get("tags") or []),
    }


def check_dom(status, dom: str, now=None) -> List[str]:
    want = expected(status, now)
    problems = []
    for key in ("badge", "video", "audio", "category", "title"):
        got = element_text(dom, key)
        if got is None:
            problems.append(f"{key} element is missing from the page")
        elif got != want[key]:
            problems.append(f"{key} shows {got!r}, status says {want[key]!r}")
    chips = len(re.findall(r'class="tag"', dom))
    if chips != want["tags"]:
        problems.append(f"tags shows {chips} chips, status lists {want['tags']}")
    return problems
