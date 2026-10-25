"""SABnzbd API client for pause/resume."""

import logging
import re
import psutil
import requests

log = logging.getLogger(__name__)

_APIKEY_RE = re.compile(r"(apikey=)[^&\s'\"]+")


def redact_apikey(text) -> str:
    """Return text with any apikey=<value> query parameter masked, so a
    request error that embeds the SABnzbd URL never writes the key to a log."""
    return _APIKEY_RE.sub(r"\1***", str(text))


class SABnzbdClient:
    def __init__(self, host: str, port: int, api_key: str):
        self.host = host
        self.base_url = f"http://{host}:{port}/api"
        self.api_key = api_key

    def _get(self, mode: str):
        try:
            resp = requests.get(
                self.base_url,
                params={"apikey": self.api_key, "output": "json", "mode": mode},
                timeout=3,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.warning(f"SABnzbd {mode} failed: {redact_apikey(e)}")
        return None

    def _is_local(self) -> bool:
        return self.host.lower() in ("localhost", "127.0.0.1", "::1")

    def _process_running(self) -> bool:
        """True if a SABnzbd process is in the process list."""
        for p in psutil.process_iter(["name"]):
            name = p.info.get("name")
            if name and name.lower().startswith("sabnzbd"):
                return True
        return False

    def _preflight(self, action: str) -> bool:
        """Fail fast when a local SABnzbd is not running, instead of waiting
        out the connection retries. A remote host cannot be checked by process
        list, so it always proceeds."""
        if self._is_local() and not self._process_running():
            log.warning(f"SABnzbd not running - skipping {action}")
            return False
        return True

    def pause(self):
        if not self._preflight("pause"):
            return
        result = self._get("pause")
        if result and result.get("status"):
            log.info("SABnzbd paused")
        else:
            log.warning("SABnzbd pause failed or unreachable - pause manually if needed")

    def resume(self):
        if not self._preflight("resume"):
            return
        result = self._get("resume")
        if result and result.get("status"):
            log.info("SABnzbd resumed")
        else:
            log.warning("SABnzbd resume failed or unreachable")

    @staticmethod
    def _paused_of(result):
        if result:
            return result.get("queue", {}).get("paused", False)
        return None

    @staticmethod
    def _downloading_of(result):
        if result:
            status = result.get("queue", {}).get("status")
            if status is None:
                return None
            return status not in ("Idle", "Paused")
        return None

    def queue_state(self):
        """(paused, downloading) from ONE mode=queue request. Each half has the
        same meaning as is_paused() / is_downloading() (None when unreachable;
        downloading is also None if the status field is missing)."""
        result = self._get("queue")
        return self._paused_of(result), self._downloading_of(result)

    def is_paused(self):
        return self._paused_of(self._get("queue"))

    def is_downloading(self):
        """True if the queue is actively working through a download (any busy
        sub-state - Downloading, Propagating, Fetching, Checking, etc.), False if
        Idle or Paused, None if the status field is missing/unreachable. Never
        infers activity from anything but SABnzbd's own reported status string."""
        return self._downloading_of(self._get("queue"))
