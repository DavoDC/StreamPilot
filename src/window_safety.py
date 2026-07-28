"""Blacklist of window executables StreamPilot must never stream.

Twitch is completely public - if OBS's Game Capture window ever resolves to
a browser, the raw desktop, or a terminal/editor (private tabs, files,
credentials, DMs), it broadcasts that to anyone watching. This is checked in
three places, deliberately redundant (defense in depth - any one of them
catches a different failure mode):
  1. config.py at daemon startup - rejects a blacklisted exe in config.json
  2. streampilot.py's add-game wizard - refuses to save a blacklisted window
  3. daemon.py's heartbeat (the important one) - reads OBS's ACTUAL live
     Game Capture window every cycle and force-stops the stream if it ever
     resolves to a blacklisted exe, regardless of how it got there (config
     edited by hand, OBS meddled with directly, a future bug elsewhere)
"""

# Lowercase exe names. Extend here if a new risk surfaces - this is the one
# place all three enforcement points read from.
BLACKLISTED_EXES = frozenset({
    # Browsers - private tabs, logged-in sessions, autofill
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "iexplore.exe",
    # Raw desktop / file browsing - file names, folder contents
    "explorer.exe", "dwm.exe",
    # Terminals / editors - source code, credentials, command history
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "notepad.exe", "code.exe",
    # OBS itself - capturing OBS's own window is a meaningless mirror loop
    "obs64.exe", "obs32.exe",
})


def extract_exe(obs_window: str | None) -> str | None:
    """Pull the executable name out of an OBS window string
    ('Title:Class:Executable.exe') or a bare exe name. None/empty -> None."""
    if not obs_window:
        return None
    return obs_window.rsplit(":", 1)[-1]


def extract_title(obs_window: str | None) -> str | None:
    """Pull the human-readable window title out of an OBS window string
    ('Title:Class:Executable.exe') - the dashboard's 'Game Captured' row
    shows this instead of the configured game name, so it reflects what's
    ACTUALLY captured. Mirrors extract_exe's convention of splitting from
    the right (Class/Executable never contain ':', but a title
    theoretically could). None for a bare exe name, an empty/None input, or
    anything that doesn't have the full 3-part shape - callers fall back
    sensibly (e.g. to the configured game name) rather than showing a
    mangled partial string."""
    if not obs_window:
        return None
    parts = obs_window.rsplit(":", 2)
    if len(parts) != 3:
        return None
    title = parts[0].strip()
    return title or None


def normalize_exe_name(exe: str | None) -> str | None:
    """Lowercase an exe name for case-insensitive comparison. None/empty ->
    None. The single shared normaliser - audio_safety.py reuses this rather
    than duplicating the lowercase-compare logic."""
    if not exe:
        return None
    return exe.lower()


def is_blacklisted(obs_window: str | None) -> bool:
    """True if obs_window (a full 'Title:Class:Exe' string or a bare exe
    name) resolves to a blacklisted executable."""
    exe = normalize_exe_name(extract_exe(obs_window))
    if not exe:
        return False
    return exe in BLACKLISTED_EXES
