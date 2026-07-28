"""Allow-list guard for OBS's "Application Audio Output Capture" source -
the audio twin of window_safety.py.

Video safety (window_safety.py) uses a blocklist because the space of safe
game windows is open-ended - anything not a browser/desktop/terminal is
fine. Audio inverts that: only exes that are keys of config.games (plus
config.audio.extra_allowed) are ever permitted in the capture list -
anything else present is a violation. The failure mode is asymmetric: a
game missing from the list costs a silent stream (embarrassing, noticed
instantly); an exe wrongly present, or the "capture all EXCEPT" box ticked,
streams Discord voice, Signal notifications and browser tabs to the public
- not noticed by the streamer at all, and cannot be taken back. An
allow-list fails closed; a blocklist fails open, and here failing open
means broadcasting a private conversation.

DENIED_EXES is defense in depth on top of the allow-list itself (a bad
config edit or a mistyped add-game could otherwise let a hard-denied exe
slip into config.games) - mirrors window_safety.BLACKLISTED_EXES, and
shares its exe-name normalisation (window_safety.normalize_exe_name)
rather than duplicating the lowercase-compare logic.

Every function here is total and never raises - a malformed settings dict
returns a "stop" violation with code "unreadable" instead of an exception,
because failing closed is the whole point of this module.
"""

from dataclasses import dataclass

import window_safety

# Lowercase, WITH the .exe suffix - same convention as
# window_safety.BLACKLISTED_EXES. Never permitted in the audio capture
# list even if a config edit somehow put one under config.games.
DENIED_EXES = frozenset({
    # Browsers - private tabs, logged-in sessions
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "iexplore.exe",
    # Chat / voice apps - private conversations, DMs, notifications
    "discord.exe", "signal.exe", "slack.exe", "telegram.exe", "whatsapp.exe",
    "teams.exe", "zoom.exe", "skype.exe",
    # OBS itself and the raw desktop - meaningless or leaky
    "obs64.exe", "obs32.exe", "explorer.exe", "dwm.exe",
    # Terminals / editors - source code, credentials, command history
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "code.exe", "notepad.exe",
    # Personal listening - not meant for the public audience
    "spotify.exe",
})

# OBS omits keys sitting at their default value from GetInputSettings - a
# correctly configured live source has neither 'mode' nor 'exclude' present.
# Absent must resolve to these, never to "unknown and therefore unsafe".
DEFAULT_MODE = 0
DEFAULT_EXCLUDE = False

# Returned by resolve_mode when 'mode' is present but not an int (e.g. "1",
# 1.5, [1], None). Guaranteed != DEFAULT_MODE so check_audio_settings' mode
# != DEFAULT_MODE rule still fires a stop violation instead of the
# malformed value silently reading as the safe default.
UNRESOLVABLE_MODE = -1


@dataclass(frozen=True)
class Violation:
    severity: str  # "stop" or "warn"
    code: str
    message: str


def extract_capture_exes(settings: dict) -> list[str]:
    """Pull the 'value' field out of every entry of settings['executable_list'].
    Tolerant of a missing key, a non-list value, and entries that are bare
    strings rather than dicts - never raises."""
    if not isinstance(settings, dict):
        return []
    entries = settings.get("executable_list")
    if not isinstance(entries, list):
        return []
    exes = []
    for entry in entries:
        if isinstance(entry, dict):
            value = entry.get("value")
            if isinstance(value, str) and value:
                exes.append(value)
        elif isinstance(entry, str) and entry:
            exes.append(entry)
    return exes


def resolve_mode(settings: dict) -> int:
    """Return settings['mode'] if present, else the documented default (0 =
    capture selected executables).

    A present-but-not-int value is resolved to UNRESOLVABLE_MODE rather than
    falling back to the default. Only an ABSENT key means "default". This
    matters because mode selects capture-selected vs capture-all-except, so
    a surprising value ("1", 1.5, None) must fail closed, not silently read
    as safe."""
    if not isinstance(settings, dict):
        return DEFAULT_MODE
    if "mode" not in settings:
        return DEFAULT_MODE
    value = settings["mode"]
    return value if isinstance(value, int) else UNRESOLVABLE_MODE


def resolve_exclude(settings: dict) -> bool:
    """Return settings['exclude'] if present, else the documented default
    (False = do not invert the capture list).

    A present-but-not-bool value is resolved by truthiness rather than
    falling back to the default. Only an ABSENT key means "default". This
    matters because exclude=True is the single worst violation, so a
    surprising value (1, "true") must fail closed, not silently read as
    safe."""
    if not isinstance(settings, dict):
        return DEFAULT_EXCLUDE
    if "exclude" not in settings:
        return DEFAULT_EXCLUDE
    return bool(settings["exclude"])


def check_audio_settings(settings: dict, allowed_exes: set) -> list["Violation"]:
    """Evaluate an audio-capture source's settings against the allow-list.

    Severity order (worst first):
      1. exclude=True            -> stop, "exclude_inverted"
      2. mode != 0                -> stop, "wrong_mode"
      3. denied exe present       -> stop, "denied_exe" (one per exe)
      4. unknown (non-allowed) exe -> stop, "unknown_exe" (one per exe)
      5. empty capture list        -> warn, "empty_list"

    Never raises - malformed `settings` returns a single "unreadable" stop
    violation.
    """
    try:
        if not isinstance(settings, dict):
            return [Violation(
                "stop", "unreadable",
                "Audio capture settings could not be read (not a dict) - refusing to stream",
            )]

        violations: list[Violation] = []

        if resolve_exclude(settings):
            violations.append(Violation(
                "stop", "exclude_inverted",
                "The 'Capture all audio EXCEPT selected executables' box is ticked - "
                "this inverts the capture list and would leak every other app's audio",
            ))

        mode = resolve_mode(settings)
        if mode != DEFAULT_MODE:
            raw_mode = settings.get("mode")
            if "mode" in settings and not isinstance(raw_mode, int):
                message = (
                    f"Audio capture mode is {raw_mode!r} (not a recognised int), "
                    f"expected {DEFAULT_MODE} (capture selected executables)"
                )
            else:
                message = f"Audio capture mode is {mode}, expected {DEFAULT_MODE} (capture selected executables)"
            violations.append(Violation("stop", "wrong_mode", message))

        allowed_lower = {window_safety.normalize_exe_name(e) for e in allowed_exes if e}
        exes = extract_capture_exes(settings)

        denied_lower = set()
        for exe in exes:
            norm = window_safety.normalize_exe_name(exe)
            if norm in DENIED_EXES:
                denied_lower.add(norm)
                violations.append(Violation(
                    "stop", "denied_exe",
                    f"'{exe}' is a hard-denied executable and must never appear in the audio capture list",
                ))

        for exe in exes:
            norm = window_safety.normalize_exe_name(exe)
            if norm in denied_lower:
                continue
            if norm not in allowed_lower:
                violations.append(Violation(
                    "stop", "unknown_exe",
                    f"'{exe}' is not a known game or an allowed exe - refusing to stream with it in the audio capture list",
                ))

        if not exes:
            violations.append(Violation(
                "warn", "empty_list",
                "Audio capture list is empty - no game audio will be captured",
            ))

        return violations
    except Exception:
        return [Violation(
            "stop", "unreadable",
            "Audio capture settings could not be evaluated - refusing to stream",
        )]


def check_missing_game(settings: dict, game_exe: str | None) -> "Violation | None":
    """Warn (never stop) when the currently-running game's exe is absent
    from the capture list - the risk here is silence, not leakage."""
    try:
        if not game_exe:
            return None
        exes = {window_safety.normalize_exe_name(e) for e in extract_capture_exes(settings)}
        if window_safety.normalize_exe_name(game_exe) not in exes:
            return Violation(
                "warn", "game_missing",
                f"'{game_exe}' is not in the audio capture list - its audio may not be streaming",
            )
        return None
    except Exception:
        return None
