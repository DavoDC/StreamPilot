"""Tests for hot_reload.py"""

import os
from unittest.mock import patch

import hot_reload


def test_snapshot_returns_mtimes_for_py_files_only(tmp_path):
    py_file = tmp_path / "a.py"
    py_file.write_text("x = 1")
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("ignored")

    snap = hot_reload.snapshot(str(tmp_path))

    assert str(py_file) in snap
    assert str(txt_file) not in snap


def test_snapshot_recurses_into_subdirectories(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    nested = sub / "b.py"
    nested.write_text("y = 2")

    snap = hot_reload.snapshot(str(tmp_path))

    assert str(nested) in snap


def test_snapshot_includes_extra_files(tmp_path):
    """config.json isn't a .py file and isn't under src/ - extra_files lets
    the watcher react to it anyway (e.g. so a config edit picks up too)."""
    py_file = tmp_path / "a.py"
    py_file.write_text("x = 1")
    config_file = tmp_path / "config.json"
    config_file.write_text("{}")

    snap = hot_reload.snapshot(str(tmp_path), extra_files=[str(config_file)])

    assert str(py_file) in snap
    assert str(config_file) in snap


def test_snapshot_missing_extra_file_ignored(tmp_path):
    snap = hot_reload.snapshot(str(tmp_path), extra_files=["/nonexistent/path.json"])
    assert "/nonexistent/path.json" not in snap


def test_check_syntax_valid_python(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    ok, err = hot_reload.check_syntax(str(tmp_path))
    assert ok is True
    assert err is None


def test_check_syntax_detects_syntax_error(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n")
    ok, err = hot_reload.check_syntax(str(tmp_path))
    assert ok is False
    assert "bad.py" in err


def test_watch_loop_restarts_after_debounce_and_valid_syntax(tmp_path):
    """The core contract: once the file set has been stable for
    debounce_seconds AND passes a syntax check, restart via os.execv."""
    baseline = {"a.py": 100.0}
    changed = {"a.py": 200.0}

    with patch("hot_reload.time.sleep"), \
         patch("hot_reload.snapshot", side_effect=[baseline, changed, changed]), \
         patch("hot_reload.time.time", side_effect=[1000.0, 1005.0]), \
         patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload.os.execv", side_effect=SystemExit) as mock_execv:
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0, debounce_seconds=2.0)
        except SystemExit:
            pass

    mock_execv.assert_called_once()


def test_watch_loop_does_not_restart_while_still_changing(tmp_path):
    """A file that keeps changing every poll must never trigger a restart -
    this is the debounce contract: only a QUIET period counts."""
    snaps = [{"a.py": 100.0}, {"a.py": 200.0}, {"a.py": 300.0}]

    with patch("hot_reload.time.sleep", side_effect=[None, None, StopIteration]), \
         patch("hot_reload.snapshot", side_effect=snaps), \
         patch("hot_reload.os.execv") as mock_execv:
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0)
        except StopIteration:
            pass

    mock_execv.assert_not_called()


def test_watch_loop_skips_restart_on_syntax_error(tmp_path):
    """A half-written feature that doesn't parse must not crash the live
    process - keep the old (working) process running instead."""
    baseline = {"a.py": 100.0}
    changed = {"a.py": 200.0}

    with patch("hot_reload.time.sleep", side_effect=[None, None, StopIteration]), \
         patch("hot_reload.snapshot", side_effect=[baseline, changed, changed]), \
         patch("hot_reload.time.time", side_effect=[1000.0, 1005.0]), \
         patch("hot_reload.check_syntax", return_value=(False, "a.py: invalid syntax")), \
         patch("hot_reload.os.execv") as mock_execv:
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0, debounce_seconds=2.0)
        except StopIteration:
            pass

    mock_execv.assert_not_called()


def test_watch_loop_sets_restart_env_var_before_execv(tmp_path):
    """Must set the restart flag BEFORE execv - streampilot.py reads it after
    the re-exec to decide whether to skip opening another browser tab."""
    baseline = {"a.py": 100.0}
    changed = {"a.py": 200.0}
    os.environ.pop(hot_reload.RESTART_ENV_VAR, None)

    with patch("hot_reload.time.sleep"), \
         patch("hot_reload.snapshot", side_effect=[baseline, changed, changed]), \
         patch("hot_reload.time.time", side_effect=[1000.0, 1005.0]), \
         patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload.os.execv", side_effect=SystemExit):
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0, debounce_seconds=2.0)
        except SystemExit:
            pass

    assert os.environ.get(hot_reload.RESTART_ENV_VAR) == "1"
    os.environ.pop(hot_reload.RESTART_ENV_VAR, None)


def test_watch_loop_does_not_restart_when_nothing_changed(tmp_path):
    """No change between polls -> no restart. Loop is stopped for the test
    via a sleep side_effect that raises after the second poll."""
    same = {"a.py": 100.0}

    with patch("hot_reload.time.sleep", side_effect=[None, StopIteration]), \
         patch("hot_reload.snapshot", return_value=same), \
         patch("hot_reload.os.execv") as mock_execv:
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0)
        except StopIteration:
            pass

    mock_execv.assert_not_called()


def test_start_watcher_launches_daemon_thread():
    with patch("hot_reload.threading.Thread") as mock_thread_cls:
        mock_thread = mock_thread_cls.return_value
        t = hot_reload.start_watcher("some_dir")

    mock_thread_cls.assert_called_once_with(
        target=hot_reload.watch_loop, args=("some_dir", hot_reload.POLL_SECONDS, None), daemon=True
    )
    mock_thread.start.assert_called_once()
    assert t is mock_thread


def test_start_watcher_passes_extra_files_through():
    with patch("hot_reload.threading.Thread") as mock_thread_cls:
        hot_reload.start_watcher("some_dir", extra_files=["config.json"])

    mock_thread_cls.assert_called_once_with(
        target=hot_reload.watch_loop, args=("some_dir", hot_reload.POLL_SECONDS, ["config.json"]), daemon=True
    )
