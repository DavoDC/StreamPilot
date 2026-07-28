"""Tests for window_safety.py - the blacklist that stops StreamPilot from
ever streaming a non-game window (browser, desktop, terminal, etc.) to a
public Twitch audience."""

import window_safety


def test_extract_exe_from_obs_window_format():
    assert window_safety.extract_exe("My Game  [id]:UnrealWindow:MyGame.exe") == "MyGame.exe"


def test_extract_exe_handles_bare_exe_name():
    assert window_safety.extract_exe("chrome.exe") == "chrome.exe"


def test_extract_exe_none_for_empty_or_none():
    assert window_safety.extract_exe("") is None
    assert window_safety.extract_exe(None) is None


def test_is_blacklisted_matches_case_insensitively():
    assert window_safety.is_blacklisted("Chrome.EXE") is True
    assert window_safety.is_blacklisted("chrome.exe") is True


def test_is_blacklisted_true_for_explorer():
    assert window_safety.is_blacklisted("explorer.exe") is True


def test_is_blacklisted_true_for_common_browsers():
    for exe in ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]:
        assert window_safety.is_blacklisted(exe) is True, exe


def test_is_blacklisted_true_for_terminals_and_editors():
    for exe in ["cmd.exe", "powershell.exe", "pwsh.exe", "WindowsTerminal.exe", "notepad.exe", "Code.exe"]:
        assert window_safety.is_blacklisted(exe) is True, exe


def test_is_blacklisted_true_for_obs_itself():
    assert window_safety.is_blacklisted("obs64.exe") is True


def test_is_blacklisted_false_for_a_game():
    assert window_safety.is_blacklisted("Palworld-Win64-Shipping.exe") is False
    assert window_safety.is_blacklisted("DeadByDaylight-Win64-Shipping.exe") is False


def test_is_blacklisted_accepts_full_obs_window_string():
    """Callers pass the full 'Title:Class:Exe' string, not just the exe."""
    assert window_safety.is_blacklisted("Google Chrome:Chrome_WidgetWin_1:chrome.exe") is True
    assert window_safety.is_blacklisted("My Game  [id]:UnrealWindow:MyGame.exe") is False


def test_is_blacklisted_false_for_none_or_empty():
    assert window_safety.is_blacklisted(None) is False
    assert window_safety.is_blacklisted("") is False
