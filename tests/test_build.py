"""Build provenance (WS-043, WS-045): sha, date, dirty marker, boot id; git asked once."""

import build


def _runner(outputs):
    calls = []

    def run(args):
        calls.append(args)
        for key, val in outputs.items():
            if key in args:
                return val
        return None
    return run, calls


def test_compute_reads_sha_date_and_clean_state():
    run, _ = _runner({"log": "abc1234 2026-10-12", "status": ""})
    info = build.compute(run)
    assert info["sha"] == "abc1234"
    assert info["date"] == "2026-10-12"
    assert info["dirty"] is False
    assert info["line"] == "StreamPilot abc1234 2026-10-12"


def test_compute_marks_dirty():
    run, _ = _runner({"log": "abc1234 2026-10-12", "status": " M src/a.py"})
    info = build.compute(run)
    assert info["dirty"] is True
    assert info["line"].endswith("+dirty")


def test_compute_falls_back_to_unknown_when_git_cannot_say():
    run, _ = _runner({})
    info = build.compute(run)
    assert info["sha"] == "unknown"
    assert info["dirty"] is False


def test_info_is_cached_and_carries_boot_fields(monkeypatch):
    run, calls = _runner({"log": "abc1234 2026-10-12", "status": ""})
    monkeypatch.setattr(build, "_cached", None)
    monkeypatch.setattr(build, "_git", run)
    a = build.info()
    n = len(calls)
    b = build.info()
    assert len(calls) == n  # no new git spawn
    assert a == b
    assert a["boot_id"] == build.BOOT_ID
    assert a["started_at"] == build.STARTED_AT
    assert a["app"] == "StreamPilot"
    assert isinstance(a["pid"], int)
