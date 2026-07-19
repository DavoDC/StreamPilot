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


def test_watch_loop_restarts_process_when_a_file_changes(tmp_path):
    """The core contract: once any .py file's mtime differs from the
    baseline snapshot, watch_loop must call os.execv to restart in place."""
    baseline = {"a.py": 100.0}
    changed = {"a.py": 200.0}

    with patch("hot_reload.time.sleep"), \
         patch("hot_reload.snapshot", side_effect=[baseline, changed]), \
         patch("hot_reload.os.execv", side_effect=SystemExit) as mock_execv:
        try:
            hot_reload.watch_loop("fake_dir", poll_interval=0)
        except SystemExit:
            pass

    mock_execv.assert_called_once()


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
        target=hot_reload.watch_loop, args=("some_dir", hot_reload.POLL_SECONDS), daemon=True
    )
    mock_thread.start.assert_called_once()
    assert t is mock_thread
