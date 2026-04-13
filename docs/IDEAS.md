# StreamPilot - Ideas and TODOs

## Pending

1. **Automated tests** - unit tests for config.py, obs_client.py, twitch_client.py, sabnzbd_client.py, daemon.py. Mock external services (OBS WebSocket, Twitch API, SABnzbd API). Use pytest.

## Lower Priority

- Windows toast notification for unknown game detected ("Run 'streampilot config add-game'")
- `streampilot stop` command - send stop signal to running daemon process
- Auto-start with Windows (Task Scheduler entry)
- Multi-scene support (different scene per game)
