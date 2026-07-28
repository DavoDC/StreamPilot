"""OBS WebSocket v5 client wrapper."""

import logging
import uuid

try:
    import obsws_python as obs
except ImportError:
    obs = None

log = logging.getLogger(__name__)

DEFAULT_AUDIO_SOURCE_NAME = "Application Audio Output Capture"


class OBSClient:
    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        game_capture_source: str,
        audio_source_name: str = DEFAULT_AUDIO_SOURCE_NAME,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.game_capture_source = game_capture_source
        self.audio_source_name = audio_source_name
        self._client = None

    def connect(self) -> bool:
        if obs is None:
            log.error("obsws-python not installed. Run: pip install obsws-python")
            return False
        try:
            self._client = obs.ReqClient(host=self.host, port=self.port, password=self.password, timeout=3)
            log.info("Connected to OBS WebSocket")
            return True
        except Exception as e:
            log.warning(f"OBS connection failed: {e}")
            return False

    def disconnect(self):
        if self._client:
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None

    def is_streaming(self) -> bool:
        if not self._client:
            return False
        try:
            resp = self._client.get_stream_status()
            return resp.output_active
        except Exception as e:
            log.warning(f"OBS get_stream_status failed: {e}")
            return False

    def start_stream(self):
        if not self._client:
            return
        try:
            self._client.start_stream()
            log.info("Stream started")
        except Exception as e:
            log.warning(f"OBS start_stream failed: {e}")

    def stop_stream(self):
        if not self._client:
            return
        try:
            self._client.stop_stream()
            log.info("Stream stopped")
        except Exception as e:
            log.warning(f"OBS stop_stream failed: {e}")

    def set_game_capture_window(self, obs_window: str):
        """Update the Game Capture source's window property."""
        if not self._client:
            return
        try:
            self._client.set_input_settings(
                name=self.game_capture_source,
                settings={'window': obs_window},
                overlay=True,
            )
            log.info(f"Game Capture window set to: {obs_window}")
        except Exception as e:
            log.warning(f"OBS set_input_settings failed: {e}")

    def get_game_capture_window(self) -> str | None:
        """Read back the current window setting from the Game Capture source."""
        if not self._client:
            return None
        try:
            resp = self._client.get_input_settings(name=self.game_capture_source)
            return resp.input_settings.get('window')
        except Exception as e:
            log.warning(f"OBS get_input_settings failed: {e}")
            return None

    def is_connected(self) -> bool:
        """Return True if the WebSocket connection is alive."""
        if not self._client:
            return False
        try:
            self._client.get_version()
            return True
        except Exception:
            return False

    # --- Audio privacy guard (see src/audio_safety.py) ---

    def get_audio_capture_settings(self) -> dict | None:
        """Read the configured audio source's settings. None means
        unreadable (source missing, OBS unreachable) - callers MUST treat
        that as unverifiable and fail closed, never as 'safe'."""
        if not self._client:
            return None
        try:
            resp = self._client.get_input_settings(name=self.audio_source_name)
            return resp.input_settings
        except Exception as e:
            log.warning(f"OBS get_input_settings failed for '{self.audio_source_name}': {e}")
            return None

    def set_audio_capture_exes(self, exe_values: list[str]) -> bool:
        """Add every exe in exe_values to the audio source's executable_list
        if not already present, preserving each existing entry's uuid/
        hidden/selected and generating a fresh uuid4 for new ones. Only
        ever adds - never removes an existing entry, even one not in
        exe_values. Auto-removal is deliberately not implemented: a wrong
        removal is invisible, so the safe response to a leak is stopping
        the stream and telling the human, not silently editing this list
        further (see docs/HISTORY.md 'Audio privacy guard')."""
        if not self._client:
            return False
        try:
            current = self.get_audio_capture_settings()
            if current is None:
                # Can't read the current list - writing blind would replace
                # it with only the new entries and silently drop everything
                # else already there. Refuse instead.
                return False
            existing = current.get("executable_list") or []
            existing_values = {e.get("value") for e in existing if isinstance(e, dict)}

            new_list = list(existing)
            added = []
            for exe in exe_values:
                if exe not in existing_values:
                    new_list.append({
                        "hidden": False,
                        "selected": False,
                        "uuid": str(uuid.uuid4()),
                        "value": exe,
                    })
                    added.append(exe)

            self._client.set_input_settings(
                name=self.audio_source_name,
                settings={"executable_list": new_list},
                overlay=True,
            )
            if added:
                log.info(f"Audio capture list updated: added {added}")
            return True
        except Exception as e:
            log.warning(f"OBS set_audio_capture_exes failed: {e}")
            return False

    def get_input_mute(self, name: str) -> bool:
        """Mute state of an input. Fails closed - returns False ('not
        muted', a potential leak) on any error, the opposite bias from most
        of this client's other getters (which fail toward 'nothing risky is
        happening'). This one guards audio privacy, so an unreadable mute
        state must never be silently treated as safe."""
        if not self._client:
            return False
        try:
            resp = self._client.get_input_mute(name=name)
            return bool(resp.input_muted)
        except Exception as e:
            log.warning(f"OBS get_input_mute failed for '{name}': {e}")
            return False

    def get_input_volume_db(self, name: str) -> float:
        """Volume in dB. Fails closed - returns 0.0 (full volume) on any
        error, same rationale as get_input_mute."""
        if not self._client:
            return 0.0
        try:
            resp = self._client.get_input_volume(name=name)
            return float(resp.input_volume_db)
        except Exception as e:
            log.warning(f"OBS get_input_volume_db failed for '{name}': {e}")
            return 0.0

    def list_inputs_by_kind(self, kind: str) -> list[str]:
        """Names of every input whose inputKind matches `kind`. Empty list
        on any failure - the primary fail-closed protection for OBS being
        unreachable lives in get_audio_capture_settings() returning None,
        which callers must already treat as a stop condition."""
        if not self._client:
            return []
        try:
            resp = self._client.get_input_list()
            return [inp["inputName"] for inp in resp.inputs if inp.get("inputKind") == kind]
        except Exception as e:
            log.warning(f"OBS get_input_list failed: {e}")
            return []
