# Twitch API Reference

## Looking Up Game IDs

**Best tool: TwitchInsights** - `https://twitchinsights.net/game/<game_id>`

- Returns game name, viewer stats, streamer counts updated every 15 minutes
- Works without authentication - no API key needed
- Use to verify a game ID before adding it to `config/config.json`

Example lookups:
- `https://twitchinsights.net/game/491487` -> Dead by Daylight
- `https://twitchinsights.net/game/1264310518` -> Marvel Rivals

## Known Game IDs

| Game | Twitch Game ID | Verified via |
|------|---------------|--------------|
| Dead by Daylight | 491487 | TwitchInsights |
| Marvel Rivals | 1264310518 | TwitchInsights + Grok |

## Twitch Helix API

Base URL: `https://api.twitch.tv/helix/`

Requires per-request headers:
- `Client-Id: <your_client_id>`
- `Authorization: Bearer <oauth_token>`

The OAuth token in `config.json` is a user token (not an app token). It can expire.
To look up a game by ID: `GET /helix/games?id=<game_id>`
To look up by name: `GET /helix/games?name=Marvel+Rivals`

### App Access Token (no user login needed)

Requires a client secret (not stored in config). Get one from the Twitch Developer Console.
```
POST https://id.twitch.tv/oauth2/token
  client_id=<id>&client_secret=<secret>&grant_type=client_credentials
```

The StreamPilot config uses a user OAuth token (`oauth_token`) which is sufficient for
setting stream title/game - it does not need an app token for normal operation.
