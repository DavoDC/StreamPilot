"""StreamPilot polling daemon - detects game launches and drives OBS/Twitch/SABnzbd."""

import logging
import os
import subprocess
import time
from datetime import datetime
import psutil

HEARTBEAT_EVERY = 2  # polls (~4s at 2s poll interval)

from obs_client import OBSClient
from twitch_client import TwitchClient
from sabnzbd_client import SABnzbdClient

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.poll_interval = cfg.get("poll_interval_seconds", 2)
        self.games = cfg.get("games", {})

        self.obs = OBSClient(
            host=cfg["obs"]["host"],
            port=cfg["obs"]["port"],
            password=cfg["obs"]["password"],
            game_capture_source=cfg["obs"]["game_capture_source"],
        )
        self.twitch = TwitchClient(
            client_id=cfg["twitch"]["client_id"],
            oauth_token=cfg["twitch"]["oauth_token"],
        )

        sab_cfg = cfg.get("sabnzbd", {})
        self.sab_enabled = sab_cfg.get("enabled", False)
        self.sab = SABnzbdClient(
            host=sab_cfg.get("host", "localhost"),
            port=sab_cfg.get("port", 8080),
            api_key=sab_cfg.get("api_key", ""),
        ) if self.sab_enabled else None

        self._active_game_exe = None
        self._running = False

    def _ensure_obs_running(self) -> bool:
        """Launch OBS if not running, wait for WebSocket. Returns True if already connected."""
        obs_running = any(p.name().lower() == "obs64.exe" for p in psutil.process_iter(['name']))
        if obs_running:
            log.info("OBS already running.")
            return False  # not yet connected - caller will connect normally

        exe_path = self.cfg["obs"].get("exe_path")
        if not exe_path:
            log.warning("OBS not running and obs.exe_path not set in config - cannot auto-launch.")
            return False

        print("[StreamPilot] OBS not running - launching OBS...")
        log.info(f"Launching OBS: {exe_path}")
        obs_dir = os.path.dirname(os.path.abspath(exe_path))
        subprocess.Popen([exe_path], cwd=obs_dir)

        # Wait up to 30s for WebSocket to become available
        for attempt in range(15):
            time.sleep(2)
            if self.obs.connect():
                print("[StreamPilot] OBS ready.")
                log.info("OBS WebSocket connected after launch.")
                return True  # already connected
            log.info(f"Waiting for OBS WebSocket... (attempt {attempt + 1}/15)")

        log.error("OBS did not become ready within 30s.")
        return False

    def start(self):
        log.info("StreamPilot daemon starting...")
        already_connected = self._ensure_obs_running()
        if not already_connected and not self.obs.connect():
            log.error("Could not connect to OBS WebSocket. Is OBS running with WebSocket enabled?")
            return

        self.twitch.validate()
        self._running = True

        try:
            self._loop()
        except KeyboardInterrupt:
            log.info("Daemon stopped by user.")
        finally:
            self._on_no_game()
            self.obs.disconnect()

    def stop(self):
        self._running = False

    def _loop(self):
        log.info(f"Polling every {self.poll_interval}s for known games: {list(self.games.keys())}")
        poll_count = 0
        while self._running:
            detected = self._detect_game()
            if detected != self._active_game_exe:
                if detected:
                    self._on_game_launch(detected)
                else:
                    self._on_no_game()
                self._active_game_exe = detected
            poll_count += 1
            if poll_count % HEARTBEAT_EVERY == 0:
                self._print_heartbeat()
            time.sleep(self.poll_interval)

    def _format_heartbeat(
        self,
        timestamp: str,
        game_name: str | None,
        obs_streaming: bool,
        twitch_category: str | None,
        sab_paused: bool | None,
    ) -> str:
        game_active = game_name is not None

        game_str = game_name if game_active else "Idle"
        cat_str = twitch_category if twitch_category else "Unknown"

        if not self.sab_enabled:
            sab_str = "Disabled"
        elif sab_paused is None:
            sab_str = "Unreachable"
        elif sab_paused:
            sab_str = "Paused"
        elif game_active:
            sab_str = "RUNNING - should be paused"
        else:
            sab_str = "Running"

        issue = game_active and (not obs_streaming or not sab_paused or sab_paused is None)
        status = "ISSUE" if issue else "OK"

        return f"[{timestamp}] Status: {status} | Streaming: {game_str} | Category: {cat_str} | SABnzbd: {sab_str}"

    def _print_heartbeat(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        game_name = self.games.get(self._active_game_exe, {}).get("name") if self._active_game_exe else None
        obs_streaming = self.obs.is_streaming()
        twitch_category = self.twitch.get_current_game_name()
        sab_paused = self.sab.is_paused() if (self.sab_enabled and self.sab) else None
        print(self._format_heartbeat(timestamp, game_name, obs_streaming, twitch_category, sab_paused))

    def _detect_game(self):
        """Return exe name of first known running game, or None."""
        running = {p.name() for p in psutil.process_iter(['name'])}
        for exe in self.games:
            if exe in running:
                return exe
        return None

    def _on_game_launch(self, exe: str):
        game = self.games[exe]
        name = game["name"]
        log.info(f"Game detected: {name} ({exe})")
        print(f"[StreamPilot] {name} detected")

        self.obs.set_game_capture_window(game["obs_window"])
        self.twitch.set_game(game["twitch_game_id"])

        if self.obs.is_streaming():
            self.obs.stop_stream()
            print(f"[StreamPilot] Ending previous VOD")
        self.obs.start_stream()
        print(f"[StreamPilot] Stream started for {name}")

        if self.sab_enabled and self.sab:
            self.sab.pause()
            print("[StreamPilot] SABnzbd paused")

    def _on_no_game(self):
        if self._active_game_exe is None:
            return
        log.info("No game detected - stopping stream")
        print("[StreamPilot] Game exited - stopping stream")

        if self.obs.is_streaming():
            self.obs.stop_stream()

        if self.sab_enabled and self.sab:
            self.sab.resume()
            print("[StreamPilot] SABnzbd resumed")

    def get_status(self) -> dict:
        streaming = self.obs.is_streaming() if self.obs._client else False
        sab_paused = self.sab.is_paused() if (self.sab_enabled and self.sab) else None
        return {
            "active_game": self.games.get(self._active_game_exe, {}).get("name") if self._active_game_exe else None,
            "streaming": streaming,
            "sabnzbd_paused": sab_paused,
        }
