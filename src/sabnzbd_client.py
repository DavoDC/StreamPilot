"""SABnzbd API client for pause/resume."""

import logging
import requests

log = logging.getLogger(__name__)


class SABnzbdClient:
    def __init__(self, host: str, port: int, api_key: str):
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
            log.warning(f"SABnzbd {mode} failed: {e}")
        return None

    def pause(self):
        result = self._get("pause")
        if result and result.get("status"):
            log.info("SABnzbd paused")
        else:
            log.warning("SABnzbd pause failed or unreachable - pause manually if needed")

    def resume(self):
        result = self._get("resume")
        if result and result.get("status"):
            log.info("SABnzbd resumed")
        else:
            log.warning("SABnzbd resume failed or unreachable")

    def is_paused(self):
        result = self._get("queue")
        if result:
            return result.get("queue", {}).get("paused", False)
        return None

    def is_downloading(self):
        """True if the queue is actively working through a download (any busy
        sub-state - Downloading, Propagating, Fetching, Checking, etc.), False if
        Idle or Paused, None if the status field is missing/unreachable. Never
        infers activity from anything but SABnzbd's own reported status string."""
        result = self._get("queue")
        if result:
            status = result.get("queue", {}).get("status")
            if status is None:
                return None
            return status not in ("Idle", "Paused")
        return None
