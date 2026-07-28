"""Read-only probe of a live OBS instance's audio-capture input sources.

Connects using obsws-python (see src/obs_client.py for the connection pattern)
with credentials from config/config.json, then reports:

  1. All input kinds (highlighting "audio"/"wasapi" kinds)
  2. All inputs (name + kind)
  3. Full settings + default settings for every audio/wasapi input
  4. Candidate list-property items for those inputs
  5. OBS + obs-websocket version info

This script NEVER calls any Set* request - it is strictly read-only against
the live OBS instance. Full raw output is also written to
data/logs/probe-audio-source.log.

Usage:
    python scripts/probe_audio_source.py
"""

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "config.json"
LOG_PATH = REPO_ROOT / "data" / "logs" / "probe-audio-source.log"

try:
    import obsws_python as obs
except ImportError:
    obs = None

# Candidate list-property names to probe on audio/wasapi inputs.
CANDIDATE_PROPERTIES = [
    "window",
    "priority",
    "executables",
    "exe_list",
    "session",
    "mode",
    "device_id",
]


class TeeWriter:
    """Writes to stdout and a log file simultaneously."""

    def __init__(self, log_file):
        self._log_file = log_file

    def print(self, *args, **kwargs):
        text = " ".join(str(a) for a in args)
        print(text, **kwargs)
        self._log_file.write(text + "\n")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_resp(resp) -> dict:
    """Best-effort dict dump of an obsws_python dataclass-like response."""
    try:
        attrs_fn = getattr(resp, "attrs", None)
        if callable(attrs_fn):
            names = attrs_fn()
            return {name: getattr(resp, name, None) for name in names}
    except Exception:
        pass
    # Fallback: raw vars(), filtering out dunder/internal entries.
    return {k: v for k, v in vars(resp).items() if not k.startswith("__")}


def is_audio_kind(kind: str) -> bool:
    if not kind:
        return False
    k = kind.lower()
    return "audio" in k or "wasapi" in k


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_PATH, "w", encoding="utf-8")
    out = TeeWriter(log_file)

    out.print(f"=== OBS audio source probe - {time.strftime('%Y-%m-%d %H:%M:%S')} ===")

    if obs is None:
        out.print("ERROR: obsws-python is not installed. Run: pip install obsws-python")
        log_file.close()
        return 1

    try:
        config = load_config()
    except Exception as e:
        out.print(f"ERROR: failed to load config: {e}")
        log_file.close()
        return 1

    obs_cfg = config.get("obs", {})
    host = obs_cfg.get("host", "localhost")
    port = obs_cfg.get("port", 4455)
    password = obs_cfg.get("password", "")

    out.print(f"Connecting to OBS WebSocket at {host}:{port} ...")
    try:
        client = obs.ReqClient(host=host, port=port, password=password, timeout=5)
    except Exception as e:
        out.print(f"ERROR: could not connect to OBS ({host}:{port}): {e}")
        out.print("OBS may not be running, or the WebSocket server may be disabled.")
        out.print("Not attempting to launch OBS (read-only probe).")
        log_file.close()
        return 1

    out.print("Connected.\n")

    # --- 5. Version info ---
    out.print("--- OBS / obs-websocket version ---")
    try:
        ver = client.get_version()
        ver_dump = dump_resp(ver)
        obs_version = ver_dump.get("obs_version")
        ws_version = ver_dump.get("obs_web_socket_version")
        out.print(f"obsVersion: {obs_version}")
        out.print(f"obsWebSocketVersion: {ws_version}")
        out.print("Full version response:")
        out.print(json.dumps(ver_dump, indent=2, default=str))
    except Exception as e:
        out.print(f"ERROR calling get_version(): {e}")
    out.print("")

    # --- 1. Input kind list ---
    out.print("--- Input kinds (GetInputKindList) ---")
    all_kinds = []
    try:
        kinds_resp = client.get_input_kind_list(unversioned=False)
        kinds_dump = dump_resp(kinds_resp)
        all_kinds = kinds_dump.get("input_kinds", []) or []
        out.print(f"Total kinds: {len(all_kinds)}")
        for k in all_kinds:
            flag = "  <-- AUDIO/WASAPI" if is_audio_kind(k) else ""
            out.print(f"  {k}{flag}")
    except Exception as e:
        out.print(f"ERROR calling get_input_kind_list(): {e}")
    out.print("")

    # --- 2. Input list ---
    out.print("--- Inputs (GetInputList) ---")
    all_inputs = []
    try:
        inputs_resp = client.get_input_list()
        inputs_dump = dump_resp(inputs_resp)
        all_inputs = inputs_dump.get("inputs", []) or []
        out.print(f"Total inputs: {len(all_inputs)}")
        for inp in all_inputs:
            name = inp.get("inputName")
            kind = inp.get("inputKind")
            flag = "  <-- AUDIO/WASAPI" if is_audio_kind(kind) else ""
            out.print(f"  name={name!r} kind={kind!r}{flag}")
    except Exception as e:
        out.print(f"ERROR calling get_input_list(): {e}")
    out.print("")

    audio_inputs = [
        inp for inp in all_inputs if is_audio_kind(inp.get("inputKind", ""))
    ]

    if not audio_inputs:
        out.print("No audio/wasapi inputs found - nothing further to probe.")
        log_file.close()
        return 0

    # --- 3. Settings + default settings for each audio input ---
    out.print(f"--- Settings for {len(audio_inputs)} audio/wasapi input(s) ---\n")
    default_settings_cache = {}
    for inp in audio_inputs:
        name = inp.get("inputName")
        kind = inp.get("inputKind")
        out.print(f"=== Input: {name!r}  (inputKind={kind!r}) ===")

        try:
            settings_resp = client.get_input_settings(name=name)
            settings_dump = dump_resp(settings_resp)
            out.print(f"get_input_settings({name!r}) -> full response:")
            out.print(json.dumps(settings_dump, indent=2, default=str))
        except Exception as e:
            out.print(f"ERROR calling get_input_settings({name!r}): {e}")
        out.print("")

        if kind not in default_settings_cache:
            try:
                default_resp = client.get_input_default_settings(kind=kind)
                default_dump = dump_resp(default_resp)
                default_settings_cache[kind] = default_dump
            except Exception as e:
                out.print(f"ERROR calling get_input_default_settings({kind!r}): {e}")
                default_settings_cache[kind] = None

        out.print(f"get_input_default_settings({kind!r}) -> full response:")
        out.print(json.dumps(default_settings_cache[kind], indent=2, default=str))
        out.print("")

        # --- 4. Candidate list-property items ---
        out.print(f"--- Candidate property probes for {name!r} ---")
        succeeded = []
        for prop in CANDIDATE_PROPERTIES:
            try:
                prop_resp = client.get_input_properties_list_property_items(
                    input_name=name, prop_name=prop
                )
                prop_dump = dump_resp(prop_resp)
                items = prop_dump.get("property_items", [])
                truncated = items[:15]
                more = f" (+{len(items) - 15} more)" if len(items) > 15 else ""
                out.print(
                    f"  [OK] {prop!r}: {len(items)} item(s){more}\n"
                    f"       {json.dumps(truncated, indent=2, default=str)}"
                )
                succeeded.append(prop)
            except Exception as e:
                out.print(f"  [FAIL] {prop!r}: {e}")
        out.print(f"Succeeded properties for {name!r}: {succeeded}")
        out.print("")

    try:
        client.disconnect()
    except Exception:
        pass

    out.print("=== Probe complete ===")
    log_file.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
