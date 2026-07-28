"""Read-only end-to-end check of the audio privacy guard against a live OBS
instance.

Loads the real config, connects to the live OBS at obs.host:obs.port, fetches
the real "Application Audio Output Capture" settings, and runs
audio_safety.check_audio_settings against them. Separately checks Desktop
Audio and Mic/Aux inputs for a leak (not muted and above -60 dB), the same
way daemon.py's _check_desktop_audio_leak does.

This script NEVER calls any Set* request - it is strictly read-only, safe to
run against a real streaming setup at any time.

Usage:
    python scripts/check_audio_safety.py
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

import audio_safety  # noqa: E402
import config as config_module  # noqa: E402
from obs_client import OBSClient  # noqa: E402


def main() -> int:
    print(f"=== Audio privacy guard check - {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    cfg = config_module.load()
    audio_cfg = config_module.get_audio_config(cfg)
    allowed_exes = config_module.get_allowed_audio_exes(cfg)

    print(f"Audio source name: {audio_cfg['source_name']!r}")
    print(f"Allow-list ({len(allowed_exes)} exe(s)): {sorted(allowed_exes)}")
    print(f"enforce={audio_cfg['enforce']} auto_add_game={audio_cfg['auto_add_game']} "
          f"require_desktop_audio_muted={audio_cfg['require_desktop_audio_muted']}\n")

    client = OBSClient(
        host=cfg["obs"]["host"],
        port=cfg["obs"]["port"],
        password=cfg["obs"]["password"],
        game_capture_source=cfg["obs"]["game_capture_source"],
        audio_source_name=audio_cfg["source_name"],
    )

    print(f"Connecting to OBS WebSocket at {cfg['obs']['host']}:{cfg['obs']['port']} ...")
    if not client.connect():
        print("ERROR: could not connect to OBS. Is it running with the WebSocket server enabled?")
        return 1
    print("Connected.\n")

    overall_ok = True

    # --- 1. Capture-list settings check ---
    print("--- Capture-list check ---")
    settings = client.get_audio_capture_settings()
    if settings is None:
        print("UNSAFE: could not read audio capture settings (unreadable/unavailable)")
        overall_ok = False
    else:
        print(f"Raw settings: {settings}")
        violations = audio_safety.check_audio_settings(settings, allowed_exes)
        if not violations:
            print("SAFE: capture list matches the allow-list, mode and exclude are both correct.")
        else:
            for v in violations:
                print(f"  [{v.severity.upper()}] {v.code}: {v.message}")
            if any(v.severity == "stop" for v in violations):
                overall_ok = False

    print()

    # --- 2. Desktop Audio / Mic leak check ---
    print("--- Desktop Audio / Mic leak check ---")
    leak_violations = []
    for kind, code, label in (
        ("wasapi_output_capture", "desktop_audio_live", "Desktop Audio"),
        ("wasapi_input_capture", "mic_live", "Mic/Aux"),
    ):
        names = client.list_inputs_by_kind(kind)
        print(f"{label} ({kind}) inputs: {names}")
        for name in names:
            muted = client.get_input_mute(name)
            volume_db = client.get_input_volume_db(name)
            print(f"  '{name}': muted={muted} volume_db={volume_db}")
            if muted:
                continue
            if volume_db <= -60:
                continue
            leak_violations.append(
                f"'{name}' ({label}) is live (not muted, above -60 dB) - potential audio leak"
            )

    if leak_violations:
        for msg in leak_violations:
            print(f"  [STOP] {msg}")
        overall_ok = False
    else:
        print("SAFE: no live (unmuted, above -60 dB) Desktop Audio or Mic/Aux inputs found.")

    print()

    try:
        client.disconnect()
    except Exception:
        pass

    print("=== Overall: SAFE ===" if overall_ok else "=== Overall: UNSAFE ===")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
