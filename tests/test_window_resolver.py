"""Tests for window_resolver.py (live window lookup; win32 fully mocked)."""

from unittest.mock import MagicMock, patch

import window_resolver


def _fake_win32(windows):
    """windows: list of (hwnd, visible, title, cls, pid, exe)."""
    gui = MagicMock()
    proc = MagicMock()
    psu = MagicMock()
    by_hwnd = {w[0]: w for w in windows}

    def enum(cb, extra):
        for w in windows:
            cb(w[0], extra)

    gui.EnumWindows.side_effect = enum
    gui.IsWindowVisible.side_effect = lambda h: by_hwnd[h][1]
    gui.GetWindowText.side_effect = lambda h: by_hwnd[h][2]
    gui.GetClassName.side_effect = lambda h: by_hwnd[h][3]
    proc.GetWindowThreadProcessId.side_effect = lambda h: (0, by_hwnd[h][4])
    exes = {w[4]: w[5] for w in windows}
    psu.Process.side_effect = lambda pid: MagicMock(**{"name.return_value": exes[pid]})
    return gui, proc, psu


def _patched(windows):
    gui, proc, psu = _fake_win32(windows)
    return patch.multiple("window_resolver", win32gui=gui, win32process=proc, psutil=psu)


def test_find_live_window_returns_current_title_class_exe():
    with _patched([(1, True, "ARC Raiders", "UninvitedGnu!10f5f50f", 10, "PioneerGame.exe")]):
        assert window_resolver.find_live_window("PioneerGame.exe") == \
            "ARC Raiders:UninvitedGnu!10f5f50f:PioneerGame.exe"


def test_find_live_window_ignores_invisible_untitled_and_other_exes():
    with _patched([
        (1, False, "Hidden", "C", 10, "PioneerGame.exe"),
        (2, True, "", "C", 10, "PioneerGame.exe"),
        (3, True, "Other", "C", 11, "other.exe"),
    ]):
        assert window_resolver.find_live_window("PioneerGame.exe") is None


def test_find_live_window_escapes_colons_in_title():
    with _patched([(1, True, "A:B", "Cls", 10, "g.exe")]):
        assert window_resolver.find_live_window("g.exe") == "A#3AB:Cls:g.exe"


def test_find_live_window_never_returns_blacklisted_exe():
    with _patched([(1, True, "Google Chrome", "Chrome_WidgetWin_1", 10, "chrome.exe")]):
        assert window_resolver.find_live_window("chrome.exe") is None


def test_find_live_window_returns_none_when_win32_unavailable():
    with patch.multiple("window_resolver", win32gui=None, win32process=None, psutil=None):
        assert window_resolver.find_live_window("g.exe") is None


def test_resolve_prefers_live_window():
    with patch("window_resolver.find_live_window", return_value="T:NewClass:g.exe"):
        assert window_resolver.resolve_obs_window("g.exe", "T:OldClass:g.exe") == "T:NewClass:g.exe"


def test_resolve_falls_back_to_stored_when_no_live_window():
    with patch("window_resolver.find_live_window", return_value=None):
        assert window_resolver.resolve_obs_window("g.exe", "T:OldClass:g.exe") == "T:OldClass:g.exe"


def test_resolve_falls_back_to_stored_when_lookup_raises():
    with patch("window_resolver.find_live_window", side_effect=RuntimeError("boom")):
        assert window_resolver.resolve_obs_window("g.exe", "T:OldClass:g.exe") == "T:OldClass:g.exe"
