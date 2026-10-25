"""Twitch API client for setting stream category."""

import logging
import time
import requests

log = logging.getLogger(__name__)

HELIX_BASE = "https://api.twitch.tv/helix"

# Warn when the token has this long left (seconds), once per calendar day each.
EXPIRY_WARN_THRESHOLDS = (7 * 86400, 86400)


class TwitchClient:
    def __init__(self, client_id: str, oauth_token: str):
        self.client_id = client_id
        self.oauth_token = oauth_token.replace("oauth:", "")
        self._broadcaster_id = None
        self._expires_at = None  # epoch seconds from the validate response; None = unknown
        self._expiry_warned = set()  # (threshold, local date) already logged

    def _headers(self) -> dict:
        return {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.oauth_token}",
        }

    def validate(self) -> bool:
        """Check token validity and cache broadcaster user ID."""
        try:
            resp = requests.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {self.oauth_token}"},
                timeout=5,
            )
            if resp.status_code != 200:
                # Log the status and a fixed reason only: the error body can echo token material.
                reason = "token rejected" if resp.status_code == 401 else "unexpected response"
                log.error(f"Twitch token invalid (HTTP {resp.status_code}): {reason}")
                return False
            data = resp.json()
            self._broadcaster_id = data.get("user_id")
            expires_in = data.get("expires_in")
            if isinstance(expires_in, (int, float)) and expires_in > 0:
                self._expires_at = time.time() + expires_in
            else:
                self._expires_at = None
            log.info(f"Twitch token valid. User ID: {self._broadcaster_id}")
            return True
        except Exception as e:
            log.warning(f"Twitch validate failed: {e}")
            return False

    def warn_if_expiring(self, now: float = None) -> bool:
        """Log a WARNING when the token (per the last validate) is within a
        threshold of expiry, once per day per threshold. Makes no API call;
        returns True if a warning was logged. Unknown expiry is silent."""
        if self._expires_at is None:
            return False
        now = time.time() if now is None else now
        remaining = self._expires_at - now
        hit = [t for t in EXPIRY_WARN_THRESHOLDS if remaining <= t]
        if not hit:
            return False
        key = (min(hit), time.strftime("%Y-%m-%d", time.localtime(now)))
        if key in self._expiry_warned:
            return False
        self._expiry_warned.add(key)
        if remaining <= 0:
            log.warning("Twitch token has expired - generate a new one (docs/SETUP.md, Step 4)")
        else:
            log.warning(f"Twitch token expires in {remaining / 86400:.1f} day(s) - generate a new one soon (docs/SETUP.md, Step 4)")
        return True

    def set_channel_info(self, game_id: str = None, title: str = None, tags: list = None):
        """Set category, title, and/or tags in a single PATCH to /channels.

        Only non-None fields are included in the request body, so callers
        can update any subset of category/title/tags without touching the
        others.
        """
        if not self._broadcaster_id:
            if not self.validate():
                log.error("Cannot set Twitch channel info - token invalid")
                return
        body = {}
        if game_id is not None:
            body["game_id"] = game_id
        if title is not None:
            body["title"] = title
        if tags is not None:
            body["tags"] = tags
        try:
            resp = requests.patch(
                f"{HELIX_BASE}/channels",
                headers=self._headers(),
                params={"broadcaster_id": self._broadcaster_id},
                json=body,
                timeout=5,
            )
            if resp.status_code == 204:
                log.info(f"Twitch channel info updated: {body}")
            else:
                log.warning(f"Twitch set_channel_info failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            log.warning(f"Twitch set_channel_info error: {e}")

    def set_game(self, game_id: str):
        """Set the stream category by Twitch game ID."""
        self.set_channel_info(game_id=game_id)

    def get_current_game_name(self) -> str | None:
        """Return the live Twitch channel category name, or None if unavailable."""
        if not self._broadcaster_id:
            return None
        try:
            resp = requests.get(
                f"{HELIX_BASE}/channels",
                headers=self._headers(),
                params={"broadcaster_id": self._broadcaster_id},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    return data[0].get("game_name")
        except Exception as e:
            log.warning(f"Twitch get_current_game_name failed: {e}")
        return None

    def get_stream_started_at(self) -> str | None:
        """Return the live stream's start time (ISO 8601, from Twitch) or
        None if not currently live / unavailable. Unlike get_current_game_name
        (which reads /channels - channel info that persists whether or not
        the channel is live), this hits /streams, which only returns a row
        while the channel is actually broadcasting."""
        if not self._broadcaster_id:
            return None
        try:
            resp = requests.get(
                f"{HELIX_BASE}/streams",
                headers=self._headers(),
                params={"user_id": self._broadcaster_id},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    return data[0].get("started_at")
        except Exception as e:
            log.warning(f"Twitch get_stream_started_at failed: {e}")
        return None

    def search_game(self, name: str) -> list:
        """Search for games by name. Returns list of dicts with id and name.

        An empty list can mean either "no matches" or "the API call failed"
        (e.g. an expired/revoked OAuth token) - callers can't tell those apart
        from the return value alone, so a non-200 is always logged here rather
        than silently folded into "no results".
        """
        try:
            resp = requests.get(
                f"{HELIX_BASE}/search/categories",
                headers=self._headers(),
                params={"query": name},
                timeout=5,
            )
            if resp.status_code == 200:
                return [{"id": g["id"], "name": g["name"]} for g in resp.json().get("data", [])]
            log.warning(f"Twitch search_game failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            log.warning(f"Twitch search_game error: {e}")
        return []

    def search_game_robust(self, name: str) -> list:
        """Search by full name; if empty, retry with the first word only."""
        results = self.search_game(name)
        if results:
            return results
        words = name.split()
        if len(words) > 1:
            results = self.search_game(words[0])
        return results
