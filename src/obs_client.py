"""OBS WebSocket v5 client wrapper."""

import logging

try:
    import obsws_python as obs
except ImportError:
    obs = None

log = logging.getLogger(__name__)


class OBSClient:
    def __init__(self, host: str, port: int, password: str, game_capture_source: str):
        self.host = host
        self.port = port
        self.password = password
        self.game_capture_source = game_capture_source
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
