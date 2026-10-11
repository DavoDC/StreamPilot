"""Busy-aware before-restart hooks for hot reload (WS-014): a reload must never
restart the process mid-stream."""

from unittest.mock import patch

import pytest

import hot_reload


@pytest.fixture(autouse=True)
def _clear_hooks():
    hot_reload.clear_before_restart_hooks()
    yield
    hot_reload.clear_before_restart_hooks()


def test_busy_reason_none_without_hooks():
    assert hot_reload.busy_reason() is None


def test_busy_reason_returns_first_reason():
    hot_reload.add_before_restart_hook(lambda: None)
    hot_reload.add_before_restart_hook(lambda: "streaming Foo")
    assert hot_reload.busy_reason() == "streaming Foo"


def test_busy_reason_failing_hook_counts_as_busy():
    def boom():
        raise RuntimeError("x")
    hot_reload.add_before_restart_hook(boom)
    assert "hook" in hot_reload.busy_reason()


def test_trigger_deferred_when_busy_and_file_kept(tmp_path):
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("")
    hot_reload.add_before_restart_hook(lambda: "game live")
    with patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload._restart") as mock_restart:
        result = hot_reload._check_trigger(str(tmp_path), str(trigger))
    assert result is True
    mock_restart.assert_not_called()
    assert trigger.exists()  # kept: fires as soon as the app is idle


def test_trigger_fires_once_idle_again(tmp_path):
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("")
    state = {"busy": True}
    hot_reload.add_before_restart_hook(lambda: "live" if state["busy"] else None)
    with patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload._restart") as mock_restart:
        hot_reload._check_trigger(str(tmp_path), str(trigger))
        state["busy"] = False
        hot_reload._check_trigger(str(tmp_path), str(trigger))
    mock_restart.assert_called_once()
    assert not trigger.exists()


def test_trigger_force_overrides_busy(tmp_path):
    trigger = tmp_path / "reload.trigger"
    trigger.write_text("force")
    hot_reload.add_before_restart_hook(lambda: "game live")
    with patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload._restart") as mock_restart:
        hot_reload._check_trigger(str(tmp_path), str(trigger))
    mock_restart.assert_called_once()


def test_passive_debounce_restart_deferred_when_busy(tmp_path):
    hot_reload.add_before_restart_hook(lambda: "game live")
    calls = {"n": 0}

    def fake_snapshot(*a, **k):
        calls["n"] += 1
        if calls["n"] > 6:
            raise SystemExit
        return {"a": 1} if calls["n"] == 1 else {"a": 2}

    with patch("hot_reload.time.sleep"), \
         patch("hot_reload.snapshot", side_effect=fake_snapshot), \
         patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload._restart") as mock_restart:
        try:
            hot_reload.watch_loop("d", poll_interval=0, debounce_seconds=0,
                                  trigger_path=str(tmp_path / "none"))
        except SystemExit:
            pass
    mock_restart.assert_not_called()


def test_passive_debounce_restarts_when_idle(tmp_path):
    calls = {"n": 0}

    def fake_snapshot(*a, **k):
        calls["n"] += 1
        if calls["n"] > 6:
            raise SystemExit
        return {"a": 1} if calls["n"] == 1 else {"a": 2}

    with patch("hot_reload.time.sleep"), \
         patch("hot_reload.snapshot", side_effect=fake_snapshot), \
         patch("hot_reload.check_syntax", return_value=(True, None)), \
         patch("hot_reload._restart", side_effect=SystemExit) as mock_restart:
        try:
            hot_reload.watch_loop("d", poll_interval=0, debounce_seconds=0,
                                  trigger_path=str(tmp_path / "none"))
        except SystemExit:
            pass
    mock_restart.assert_called_once()
