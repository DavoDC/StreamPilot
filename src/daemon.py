"""StreamPilot polling daemon - detects game launches and drives OBS/Twitch/SABnzbd."""

import json
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
import audio_safety
import config as config_module
import status_file
import window_safety

log = logging.getLogger(__name__)

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'status.json')
SAB_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'state', 'sab_settings.json')


class Daemon:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.poll_interval = cfg.get("poll_interval_seconds", 2)
        self.games = cfg.get("games", {})

        self.audio_cfg = config_module.get_audio_config(cfg)
        self.obs = OBSClient(
            host=cfg["obs"]["host"],
            port=cfg["obs"]["port"],
            password=cfg["obs"]["password"],
            game_capture_source=cfg["obs"]["game_capture_source"],
            audio_source_name=self.audio_cfg["source_name"],
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
        # Dashboard toggle: whether homeostasis actively pauses SABnzbd while
        # a game is active. Off for overnight "idle streaming" (game running
        # but not actively played) so downloads keep going. Persisted so it
        # survives a hot-reload restart (os.execv) mid-session.
        self.sab_auto_manage = self._load_sab_auto_manage()
        # Set for exactly one heartbeat after the dashboard toggle turns
        # auto-pause ON - see set_sab_auto_manage(). Suppresses the ISSUE
        # flag for that heartbeat's corrective re-pause, since it's the
        # direct, expected result of the user's own click, not a fault.
        self._sab_just_enabled = False
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

    def _load_sab_auto_manage(self) -> bool:
        """Read the persisted dashboard toggle. Defaults to True (normal
        homeostasis) if the file is missing or corrupt."""
        try:
            with open(SAB_SETTINGS_PATH, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("auto_manage", True))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return True

    def _save_sab_auto_manage(self) -> None:
        try:
            os.makedirs(os.path.dirname(SAB_SETTINGS_PATH), exist_ok=True)
            tmp_path = SAB_SETTINGS_PATH + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"auto_manage": self.sab_auto_manage}, f)
            os.replace(tmp_path, SAB_SETTINGS_PATH)
        except OSError as e:
            log.warning(f"Could not persist SAB auto-manage setting: {e}")

    def set_sab_auto_manage(self, enabled: bool) -> None:
        """Dashboard toggle handler. When disabled, StreamPilot never pauses
        or resumes SABnzbd itself - David controls it manually (idle
        streaming). Disabling resumes SABnzbd immediately rather than
        leaving it paused until he does it by hand in SABnzbd's own UI;
        re-enabling lets the next heartbeat re-pause it if a game is active."""
        self.sab_auto_manage = enabled
        self._save_sab_auto_manage()
        log.info(f"SABnzbd auto-pause {'enabled' if enabled else 'disabled'}")
        if enabled:
            self._sab_just_enabled = True
        if not enabled and self.sab_enabled and self.sab:
            self.sab.resume()
            log.info("SABnzbd resumed - idle-streaming mode")

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
            game = self.games[detected]
            title = build_title(game["name"], game, self.twitch_cfg)
            tags = build_tags(game, self.twitch_cfg)
            # Re-PATCH title/tags to Twitch (no game_id - category is already
            # correct, and no stream restart) so a code-only change (e.g. a
            # title-building tweak) takes effect on the live title immediately,
            # not just on the dashboard, without waiting for the game to exit
            # and relaunch. Cheap and idempotent - same PATCH _on_game_launch
            # already sends, just without touching the category.
            self.twitch.set_channel_info(title=title, tags=tags or None)
            self._current_title = title
            self._current_tags = tags
            log.info(f"Resuming existing session for {game['name']} - stream already live, not restarting it. Reapplied title/tags to Twitch.")

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
        sab_auto_manage: bool = True,
        sab_suppress_issue: bool = False,
        audio_ok: bool = True,
        audio_violation_count: int = 0,
    ) -> dict:
        """Turn raw heartbeat readings into the shared status shape consumed by
        both the terminal log line and the dashboard JSON file."""
        game_active = game_name is not None

        # sab_str reflects only current physical truth (Running/Paused), never a
        # transient "just corrected" annotation - a one-heartbeat label is easy
        # to miss or asymmetric (e.g. no counterpart on the resume direction).
        # Corrective actions are still visible in the log line that triggers
        # them (see _print_heartbeat); sab_corrected here only affects sab_issue
        # below. See CLAUDE.md "Status/state field design".
        if not self.sab_enabled:
            sab_str = "Disabled"
        elif not sab_auto_manage:
            sab_str = "Running (manual)" if sab_paused is not True else "Paused (manual)"
        elif sab_paused is None:
            sab_str = "Unreachable"
        elif sab_paused:
            sab_str = "Paused"
        else:
            sab_str = "Running"

        # SABnzbd only contributes to ISSUE when homeostasis is actually
        # trying to manage it - David turned that off on purpose for idle
        # streaming, so a "running during game" state there is expected, not
        # a fault.
        sab_issue = sab_auto_manage and not sab_suppress_issue and (not sab_paused or sab_paused is None or sab_corrected)
        issue = game_active and (
            not obs_streaming or sab_issue
            or not obs_window_ok or stream_restarted or blacklisted_window
            or not audio_ok
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
            "audio_ok": audio_ok,
            "audio_violation_count": audio_violation_count,
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
        sab_auto_manage: bool = True,
        sab_suppress_issue: bool = False,
        audio_ok: bool = True,
        audio_violation_count: int = 0,
    ) -> str:
        c = self._classify(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window, sab_auto_manage, sab_suppress_issue, audio_ok, audio_violation_count)
        line = f"Status: {c['status'] if c['game_active'] else 'OK'} | Streaming: {c['game_str']} | Category: {c['cat_str']} | SABnzbd: {c['sab_str']}"
        if c["game_active"]:
            audio_str = "OK" if c["audio_ok"] else f"VIOLATION ({c['audio_violation_count']})"
            line += f" | Audio: {audio_str}"
        if c["game_active"] and not c["obs_window_ok"]:
            line += " | OBS Window: REAPPLIED"
        if c["game_active"] and c["stream_restarted"]:
            line += " | Stream: RESTARTED"
        if c["blacklisted_window"]:
            line += f" | SAFETY: BLOCKED non-game window '{c['blacklisted_window']}' - stream force-stopped"
        return line

    def _print_heartbeat(self):
        game_name = self.games.get(self._active_game_exe, {}).get("name") if self._active_game_exe else None
        # Only fetch/show the Twitch category while a game is active - otherwise
        # it's whatever was last set, stale and misleading next to "Idle" (also
        # skips a pointless API call while idle).
        twitch_category = self.twitch.get_current_game_name() if self._active_game_exe else None
        sab_paused = self.sab.is_paused() if (self.sab_enabled and self.sab) else None

        obs_window_ok = True
        sab_corrected = False
        stream_restarted = False
        blacklisted_window = None
        audio_ok = True
        audio_violations = []
        # Consumed once - covers only the heartbeat that actually performs
        # the corrective re-pause right after the toggle flips on.
        sab_suppress_issue = self._sab_just_enabled
        self._sab_just_enabled = False

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

            # SAFETY: audio privacy guard - re-checked every heartbeat exactly
            # like the window check above, independent of how a leak got there
            # (config drift, OBS meddled with directly). See src/audio_safety.py.
            audio_ok, audio_violations = self._check_audio_safety(self._active_game_exe)
            audio_blocked = False
            if not audio_ok and self.audio_cfg.get("enforce", True):
                stop_messages = "; ".join(v.message for v in audio_violations if v.severity == "stop")
                log.error(f"AUDIO SAFETY: force-stopping stream - {stop_messages}")
                self.obs.stop_stream()
                obs_streaming = False
                audio_blocked = True

            # Stream correction: only when WebSocket is alive (avoids restart-on-crash loop).
            # Skipped when we just force-stopped for a blacklisted window or an
            # audio leak - restarting immediately would defeat the whole point
            # of stopping it.
            if obs_live and not obs_streaming and not blacklisted_window and not audio_blocked:
                log.warning("Stream stopped while game active - restarting")
                self.obs.start_stream()
                stream_restarted = True

            # Audio list convergence: CRITICAL - only when this cycle did NOT
            # just force-stop for an audio violation. audio_blocked means the
            # guard flagged a real leak against the true current settings;
            # converging/removing here on the same cycle would silently
            # "clean up" the very evidence that caused the stop, which is
            # exactly what this design must never do (see
            # _converge_audio_capture_list docstring).
            if not audio_blocked:
                self._converge_audio_capture_list(self._active_game_exe, obs_streaming)

            # SABnzbd correction - skipped entirely when auto-manage is off
            if self.sab_enabled and self.sab and self.sab_auto_manage and sab_paused is False:
                log.warning("SABnzbd running during active game session - repausing")
                self.sab.pause()
                sab_corrected = True
        else:
            obs_streaming = self.obs.is_streaming()
            self._converge_audio_capture_list(None, obs_streaming)

        audio_violation_count = len(audio_violations)
        c = self._classify(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window, self.sab_auto_manage, sab_suppress_issue, audio_ok, audio_violation_count)
        log.info(self._format_heartbeat(game_name, obs_streaming, twitch_category, sab_paused, obs_window_ok, sab_corrected, stream_restarted, blacklisted_window, self.sab_auto_manage, sab_suppress_issue, audio_ok, audio_violation_count))
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
                sab_auto_manage=self.sab_auto_manage,
                audio_ok=audio_ok,
                audio_violations=[v.message for v in audio_violations],
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

    def _audio_allowed_exes(self, game_exe: str | None) -> set:
        """The allow-list to check the current OBS audio capture list
        against - mirrors config.get_allowed_audio_exes but reads the
        cached self.audio_cfg (matching how every other audio.* flag is
        read/tested in this class, e.g. tests mutate daemon.audio_cfg[...]
        directly) rather than recomputing from self.cfg, which would miss
        any such test-time (or runtime) mutation. See
        config.py::get_allowed_audio_exes for the exclusive vs wide-list
        rationale - exclusive_mode (default True) narrows this to just the
        currently streaming game plus extra_allowed, closing the case
        where two games happen to be running at once."""
        extra = set(self.audio_cfg.get("extra_allowed", []))
        if self.audio_cfg.get("exclusive_mode", True):
            return ({game_exe} if game_exe else set()) | extra
        return set(self.games.keys()) | extra

    def _converge_audio_capture_list(self, game_exe: str | None, obs_streaming: bool) -> None:
        """Exclusive-mode homeostasis: converge OBS's audio executable_list
        to exactly {current game} + extra_allowed while a game is active,
        and to empty once idle with no stream running. No-ops entirely when
        audio.exclusive_mode is False (the wide allow-list path is
        untouched - nothing to converge).

        CRITICAL: this is the ONE place StreamPilot is allowed to remove an
        entry from the OBS audio capture list. It exists purely to converge
        onto the single known-correct value {current game}+extra_allowed -
        it must NEVER be used to clear a violation the safety guard has
        flagged. A denied exe (Discord etc.) or an inverted 'exclude' flag
        still force-stops the stream exactly as before (see
        _check_audio_safety / _preflight_audio_check); callers must only
        invoke this on a cycle that did NOT just force-stop for an audio
        violation (see _print_heartbeat's `not audio_blocked` gate), so a
        flagged violation is never silently 'resolved' by removal - it
        stays visible until config is fixed or the game relaunches.
        """
        if not self.audio_cfg.get("exclusive_mode", True):
            return
        if game_exe:
            target = [game_exe] + list(self.audio_cfg.get("extra_allowed", []))
        elif not obs_streaming:
            target = []
        else:
            return  # no game detected but stream still active - leave list alone
        self.obs.set_audio_capture_exes(target, exact=True)

    def _check_audio_safety(self, game_exe: str | None) -> tuple[bool, list]:
        """Evaluate the audio capture source (allow-list) plus the Desktop
        Audio / Mic leak paths against the current OBS state. Returns
        (is_safe, violations) - is_safe reflects only 'stop' severity
        violations; 'warn' violations (missing game, empty list) never
        block streaming on their own. See src/audio_safety.py."""
        settings = self.obs.get_audio_capture_settings()
        if settings is None:
            violations = [audio_safety.Violation(
                "stop", "unreadable",
                f"Could not read audio capture settings for "
                f"'{self.audio_cfg['source_name']}' - refusing to treat as safe",
            )]
        else:
            violations = audio_safety.check_audio_settings(settings, self._audio_allowed_exes(game_exe))
            missing = audio_safety.check_missing_game(settings, game_exe)
            if missing:
                violations.append(missing)
                if self.audio_cfg.get("auto_add_game", True):
                    self._auto_add_game_to_audio(settings, game_exe)

        if self.audio_cfg.get("require_desktop_audio_muted", True):
            violations.extend(self._check_desktop_audio_leak())

        is_safe = not any(v.severity == "stop" for v in violations)
        return is_safe, violations

    def _auto_add_game_to_audio(self, settings: dict, game_exe: str) -> None:
        """Warn-only 'game_missing' path: add the just-launched game to the
        audio capture list so its own audio streams next time. Additive
        only - set_audio_capture_exes() never removes an existing entry."""
        exes = audio_safety.extract_capture_exes(settings)
        if self.obs.set_audio_capture_exes(exes + [game_exe]):
            log.info(f"Audio: auto-added '{game_exe}' to the capture list")

    def _check_desktop_audio_leak(self) -> list:
        """Desktop Audio / Mic sources are open microphones/system-audio
        into the stream if not muted (or effectively silent). Checked by
        input kind since these sources only expose device_id in their
        settings - mute/volume is the only readable signal."""
        violations = []
        for kind, code, label in (
            ("wasapi_output_capture", "desktop_audio_live", "Desktop Audio"),
            ("wasapi_input_capture", "mic_live", "Mic/Aux"),
        ):
            for name in self.obs.list_inputs_by_kind(kind):
                if self.obs.get_input_mute(name):
                    continue
                if self.obs.get_input_volume_db(name) <= -60:
                    continue
                violations.append(audio_safety.Violation(
                    "stop", code,
                    f"'{name}' ({label}) is live (not muted, above -60 dB) - potential audio leak",
                ))
        return violations

    def _preflight_audio_check(self, game_exe: str) -> bool:
        """Run before every start_stream() call - blocks a bad broadcast
        before it ever goes out, rather than starting then stopping."""
        is_safe, violations = self._check_audio_safety(game_exe)
        for v in violations:
            if v.severity == "stop":
                log.error(f"AUDIO SAFETY: {v.message}")
            else:
                log.warning(f"AUDIO: {v.message}")
        if not is_safe and self.audio_cfg.get("enforce", True):
            log.error("AUDIO SAFETY: blocking stream start")
            return False
        return True

    def _on_game_launch(self, exe: str):
        game = self.games[exe]
        name = game["name"]
        log.info(f"Game detected: {name} ({exe})")

        # Converge the audio capture list to this game as early as possible,
        # before anything else - addresses the win-capture-audio plugin
        # attach-timing concern (docs/HISTORY.md "Exclusive audio capture
        # list"): the exe should be in OBS's list before its audio session
        # is likely to exist, not after. No-op when exclusive_mode is False.
        self._converge_audio_capture_list(exe, obs_streaming=False)

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

        if self._preflight_audio_check(exe):
            self.obs.start_stream()
            log.info(f"Stream started for {name}")
        else:
            log.error(f"Stream NOT started for {name} - audio safety check failed")

        if self.sab_enabled and self.sab and self.sab_auto_manage:
            self.sab.pause()
            log.info("SABnzbd paused")

    def _on_no_game(self):
        if self._active_game_exe is None:
            return
        log.info("Game exited - stopping stream")

        if self.obs.is_streaming():
            self.obs.stop_stream()

        # Clear the audio capture list on game exit - no-op when
        # exclusive_mode is False. obs_streaming=False here because the
        # stream was just stopped above (or wasn't running at all).
        self._converge_audio_capture_list(None, obs_streaming=False)

        if self.sab_enabled and self.sab and self.sab_auto_manage:
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
