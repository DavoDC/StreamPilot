"""One command to check everything (WS-084): unit tests, then a fixture capture of every scenario (which runs ui_check).

  python src/verify.py [--skip tests|capture ...]

Prints one line per step with its time and one final VERIFY PASS or VERIFY FAIL line. Every step runs even after a
failure, so one run shows everything that is wrong. Exit 0 all passed, 1 a step failed, 2 bad arguments.
Fixture mode only: nothing here touches the live server on port 8765, OBS, Twitch or SABnzbd.
"""
import argparse
import os
import subprocess
import sys
import time
from typing import Callable, List, NamedTuple, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class Step(NamedTuple):
    name: str
    cmd: List[str]


PY = sys.executable
STEPS = [
    Step("tests", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", os.path.join(ROOT, "tests")]),
    Step("capture", [PY, os.path.join(HERE, "capture.py"), "--fixture"]),
]


def select(skip: Optional[List[str]] = None) -> List[Step]:
    names = {s.name for s in STEPS}
    bad = [n for n in skip or [] if n not in names]
    if bad:
        print(f"unknown step {bad}; steps are {sorted(names)}", file=sys.stderr)
        raise SystemExit(2)
    return [s for s in STEPS if s.name not in (skip or [])]


def _run(cmd: List[str]) -> int:
    return subprocess.call(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def run_all(steps: List[Step], runner: Callable[[List[str]], int] = _run, say: Callable[[str], None] = print,
            clock: Callable[[], float] = time.monotonic) -> int:
    failed, started = [], clock()
    for s in steps:
        t0 = clock()
        code = runner(s.cmd)
        say(f"  {'ok  ' if code == 0 else 'FAIL'} {s.name} ({clock() - t0:.0f}s)")
        if code != 0:
            failed.append(s.name)
    total = f"{clock() - started:.0f}s"
    say(f"VERIFY FAIL: {', '.join(failed)} ({total})" if failed else f"VERIFY PASS ({total})")
    return 1 if failed else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run unit tests and a fixture capture; one PASS or FAIL line.")
    ap.add_argument("--skip", nargs="*", default=[], help="step names to skip: " + ", ".join(s.name for s in STEPS))
    args = ap.parse_args(argv)
    return run_all(select(args.skip))


if __name__ == "__main__":
    sys.exit(main())
