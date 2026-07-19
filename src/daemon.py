"""StreamPilot polling daemon - detects game launches and drives OBS/Twitch/SABnzbd."""

import logging
import os
import subprocess
import time
import psutil

HEARTBEAT_EVERY = 1  # every poll; API calls in heartbeat provide natural throttling (~3-5s/cycle)

from obs_client import OBSClient
from twitch_client import TwitchClient
from sabnzbd_client import SABnzbdClient
from stream_meta import build_title, build_tags
import status_file
import window_safety

log = logging.getLogger(__name__)

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'status.json')


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
        self.twitch_cfg = cfg.get("twitch", {})
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
        self._current_title = None
        self._current_tags = None
        self._end_stream_on_stop = True
        # Changes every process start (including a hot-reload self-restart) so
        # the dashboard can tell "the server behind me restarted" and reload
        # itself - see hot_reload.py and the build_id check in dashboard JS.
        self.build_id = str(time.time())

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

        log.info("OBS not running - launching OBS...")
        log.info(f"Launching OBS: {exe_path}")
        obs_dir = os.path.dirname(os.path.abspath(exe_path))
        subprocess.Popen([exe_path], cwd=obs_dir)

        # Wait up to 30s for WebSocket to become available
        for attempt in range(15):
            time.sleep(2)
            if self.obs.connect():
                log.info("OBS WebSocket ready.")
                return True  # already connected
            log.info(f"Waiting for OBS WebSocket... (attempt {attempt + 1}/15)")

        log.error("OBS did not become ready within 30s.")
        return False

    def _ensure_steam_running(self) -> None:
        """Launch Steam if not running. Uses steam.exe_path from config or the default install path."""
        steam_running = any(p.name().lower() == "steam.exe" for p in psutil.process_iter(['name']))
        if steam_running:
            return

        exe_path = self.cfg.get("steam", {}).get(
            "exe_path", r"C:\Program Files (x86)\Steam\steam.exe"
        )
        if not os.path.exists(exe_path):
            log.warning(f"Steam not running and exe not found at {exe_path} - cannot auto-launch.")
            return

        log.info(f"Steam not running - launching: {exe_path}")
        steam_dir = os.path.dirname(os.path.abspath(exe_path))
        subprocess.Popen([exe_path], cwd=steam_dir)

    def start(self):
        log.info("StreamPilot daemon starting...")
        self._ensure_steam_running()
        already_connected = self._ensure_obs_running()
        if not already_connected and not self.obs.connect():
            log.error("Could not connect to OBS WebSocket. Is OBS running with WebSocket enabled?")
            return

        self.twitch.validate()
        self._reconcile_existing_session()
        self._running = True

        try:
            self._loop()
        except KeyboardInterrupt:
            log.info("Daemon stopped by user.")
        finally:
            if self._end_stream_on_stop:
                self._on_no_game()
            else:
                log.info("Quit requested with stream kept running - leaving OBS/SABnzbd as-is.")
            self.obs.disconnect()

    def _reconcile_existing_session(self):
        """Adopt an already-live stream instead of restarting it.

        A fresh Daemon always starts with _active_game_exe=None, so without
        this check, every process restart (hot-reload via --watch, or a
        manual relaunch while a game is already running) would treat an
        in-progress session as a brand-new game launch: _on_game_launch()
        stops the live stream ("Ending previous VOD") and immediately starts
        a new one, splitting the VOD and briefly erroring (OBS rejects
        StartStream while still mid-teardown) for no reason - the game never
        actually changed. If the detected game's stream is already running,
        just adopt it; the heartbeat's existing window/category drift checks
        still run every cycle as normal, so nothing is left unverified.
        """
        detected = self._detect_game()
        if detected and self.obs.is_streaming():
            self._active_game_exe = detected
            log.info(f"Resuming existing session for {self.games[detected]['name']} - stream already live, not restarting it")

    def stop(self, end_stream: bool = True):
        """Stop the polling loop. end_stream=False leaves OBS streaming and
        SABnzbd paused untouched (dashboard's "Keep streaming" quit option) -
        only the StreamPilot process itself exits."""
        self._end_stream_on_stop = end_stream
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
            else:
                time.sleep(self.poll_interval)

    def _classify(
        self,
        game_name: str | None,
        obs_streaming: bool,
        twitch_category: str | None,
        sab_paused: bool | None,
        obs_window_ok: bool = True,
        sab_corrected: bool = False,
        stream_restarted: bool = False,
        blacklisted_window: str | None = None,
    ) -> dict:
        """Turn raw heartbeat readings into the shared status shape consumed by
        both the terminal log line and the dashboard JSON file."""
        game_active = game_name is not None

        if not self.sab_enabled:
            sab_str = "Disabled"
        elif sab_paused is None:
            sab_str = "Unreachable"
        elif sab_corrected:
            sab_str = "REPAUSED"
        elif sab_paused:
            sab_str = "Paused"
        elif game_active:
            sab_str = "RUNNING - should be paused"
        else:
            sab_str = "Running"

        issue = game_active and (
            not obs_streaming or not sab_paused or sab_paused is None
            or not obs_window_ok or sab_corrected or stream_restarted or blacklisted_window
        )
        status = "ISSUE" if issue else ("OK" if game_active else "IDLE")

        return {
            "game_active": game_active,
            "game_str": game_name if game_active else "Idle",
            "cat_str": twitch_category if twitch_category else "Unknown",
            "sab_str": sab_str,
            "status": status,
            "obs_window_ok": obs_window_ok,
            "stream_restarted": stream_restarted,
            "blacklisted_window": blacklisted_window,
        }

    def _format_heartbeat(
        self,
        game_name: str | None,
        obs_streaming: bool,
        twitch_category: str | None,
        sab_paused: bool | None,
        obs_window_ok: bool = True,
        sab_corrected: bool = False,
        stream_restarted: bool = False,
        blacklisted_window: str | None = None,
    ) -> str:
        c = self._classify(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window)
        line = f"Status: {c['status'] if c['game_active'] else 'OK'} | Streaming: {c['game_str']} | Category: {c['cat_str']} | SABnzbd: {c['sab_str']}"
        if c["game_active"] and not c["obs_window_ok"]:
            line += " | OBS Window: REAPPLIED"
        if c["game_active"] and c["stream_restarted"]:
            line += " | Stream: RESTARTED"
        if c["blacklisted_window"]:
            line += f" | SAFETY: BLOCKED non-game window '{c['blacklisted_window']}' - stream force-stopped"
        return line

    def _print_heartbeat(self):
        game_name = self.games.get(self._active_game_exe, {}).get("name") if self._active_game_exe else None
        twitch_category = self.twitch.get_current_game_name()
        sab_paused = self.sab.is_paused() if (self.sab_enabled and self.sab) else None

        obs_window_ok = True
        sab_corrected = False
        stream_restarted = False
        blacklisted_window = None

        if self._active_game_exe:
            # OBS connectivity - attempt reconnect before other OBS calls
            obs_live = self.obs.is_connected()
            if not obs_live:
                log.warning("OBS WebSocket disconnected - attempting reconnect")
                if self.obs.connect():
                    obs_live = True
                    log.info("OBS WebSocket reconnected")

            obs_streaming = self.obs.is_streaming()

            # OBS window verification + correction
            expected = self.games[self._active_game_exe]["obs_window"]
            actual = self.obs.get_game_capture_window()

            # SAFETY: never stream a blacklisted window (browser/desktop/
            # terminal) - Twitch is public. Checked against OBS's ACTUAL live
            # window every heartbeat, independent of how it got there (config
            # edited by hand, OBS meddled with directly) - force-stop
            # immediately; the reapply below then restores the expected
            # (safe) game window in this same cycle.
            if window_safety.is_blacklisted(actual):
                log.error(f"SAFETY: blacklisted window captured ('{actual}') - force-stopping stream")
                self.obs.stop_stream()
                obs_streaming = False
                blacklisted_window = actual

            if actual != expected:
                log.warning(f"OBS window mismatch (expected '{expected}', got '{actual}') - reapplying")
                self.obs.set_game_capture_window(expected)
                obs_window_ok = False

            # Stream correction: only when WebSocket is alive (avoids restart-on-crash loop).
            # Skipped when we just force-stopped for a blacklisted window - restarting
            # immediately would defeat the whole point of stopping it.
            if obs_live and not obs_streaming and not blacklisted_window:
                log.warning("Stream stopped while game active - restarting")
                self.obs.start_stream()
                stream_restarted = True

            # SABnzbd correction
            if self.sab_enabled and self.sab and sab_paused is False:
                log.warning("SABnzbd running during active game session - repausing")
                self.sab.pause()
                sab_corrected = True
        else:
            obs_streaming = self.obs.is_streaming()

        c = self._classify(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window)
        log.info(self._format_heartbeat(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window))
        try:
            status_file.write_status(
                STATUS_PATH,
                status=c["status"],
                game=game_name,
                streaming=obs_streaming,
                category=twitch_category,
                sabnzbd=c["sab_str"],
                poll_interval=self.poll_interval,
                obs_window_ok=obs_window_ok,
                stream_restarted=stream_restarted,
                title=self._current_title,
                tags=self._current_tags,
                build_id=self.build_id,
                blacklisted_window=blacklisted_window,
            )
        except OSError as e:
            log.warning(f"Could not write dashboard status file: {e}")

    def _detect_game(self):
        """Return exe name of first known running game, or None.

        Reads the pre-fetched p.info['name'] (from process_iter's attrs=)
        rather than calling p.name() live - a process can exit between being
        listed and a live .name() call, raising psutil.NoSuchProcess and
        crashing the whole scan. The cached attrs value has no such race
        (psutil silently drops any process whose attrs failed to populate).
        """
        running = {p.info['name'] for p in psutil.process_iter(['name']) if p.info.get('name')}
        for exe in self.games:
            if exe in running:
                return exe
        return None

    def _on_game_launch(self, exe: str):
        game = self.games[exe]
        name = game["name"]
        log.info(f"Game detected: {name} ({exe})")

        self.obs.set_game_capture_window(game["obs_window"])

        title = build_title(name, game, self.twitch_cfg)
        tags = build_tags(game, self.twitch_cfg)
        log.info(f"Setting Twitch title: {title}")
        # Only send tags when we actually have replacements - passing an empty
        # list would wipe any existing Twitch tags, so with nothing configured
        # we leave the channel's current tags untouched (tags=None omits them).
        self.twitch.set_channel_info(
            game_id=game["twitch_game_id"], title=title, tags=tags or None
        )
        # Dashboard-visible: whatever we last SENT to Twitch, so David can
        # confirm title/tags on the dashboard without checking Twitch itself.
        self._current_title = title
        self._current_tags = tags

        if self.obs.is_streaming():
            self.obs.stop_stream()
            log.info("Ending previous VOD")
        self.obs.start_stream()
        log.info(f"Stream started for {name}")

        if self.sab_enabled and self.sab:
            self.sab.pause()
            log.info("SABnzbd paused")

    def _on_no_game(self):
        if self._active_game_exe is None:
            return
        log.info("Game exited - stopping stream")

        if self.obs.is_streaming():
            self.obs.stop_stream()

        if self.sab_enabled and self.sab:
            self.sab.resume()
            log.info("SABnzbd resumed")

        self._current_title = None
        self._current_tags = None

    def get_status(self) -> dict:
        streaming = self.obs.is_streaming() if self.obs._client else False
        sab_paused = self.sab.is_paused() if (self.sab_enabled and self.sab) else None
        return {
            "active_game": self.games.get(self._active_game_exe, {}).get("name") if self._active_game_exe else None,
            "streaming": streaming,
            "sabnzbd_paused": sab_paused,
        }
