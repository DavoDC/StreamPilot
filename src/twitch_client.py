"""Twitch API client for setting stream category."""

import logging
import requests

log = logging.getLogger(__name__)

HELIX_BASE = "https://api.twitch.tv/helix"


class TwitchClient:
    def __init__(self, client_id: str, oauth_token: str):
        self.client_id = client_id
        self.oauth_token = oauth_token.replace("oauth:", "")
        self._broadcaster_id = None

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
                log.error(f"Twitch token invalid: {resp.text}")
                return False
            data = resp.json()
            self._broadcaster_id = data.get("user_id")
            log.info(f"Twitch token valid. User ID: {self._broadcaster_id}")
            return True
        except Exception as e:
            log.warning(f"Twitch validate failed: {e}")
            return False

    def set_game(self, game_id: str):
        """Set the stream category by Twitch game ID."""
        if not self._broadcaster_id:
            if not self.validate():
                log.error("Cannot set Twitch game - token invalid")
                return
        try:
            resp = requests.patch(
                f"{HELIX_BASE}/channels",
                headers=self._headers(),
                params={"broadcaster_id": self._broadcaster_id},
                json={"game_id": game_id},
                timeout=5,
            )
            if resp.status_code == 204:
                log.info(f"Twitch category set to game ID: {game_id}")
            else:
                log.warning(f"Twitch set_game failed ({resp.status_code}): {resp.text}")
        except Exception as e:
            log.warning(f"Twitch set_game error: {e}")

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

    def search_game(self, name: str) -> list:
        """Search for games by name. Returns list of dicts with id and name."""
        try:
            resp = requests.get(
                f"{HELIX_BASE}/search/categories",
                headers=self._headers(),
                params={"query": name},
                timeout=5,
            )
            if resp.status_code == 200:
                return [{"id": g["id"], "name": g["name"]} for g in resp.json().get("data", [])]
        except Exception as e:
            log.warning(f"Twitch search_game error: {e}")
        return []
