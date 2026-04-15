# StreamPilot

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Auto-manages OBS streaming + SABnzbd when you launch a known game.

- Detects game launch via process polling
- Updates OBS Game Capture source to the game's window
- Sets Twitch category to the matching game
- Starts the stream (or swaps game mid-stream)
- Pauses SABnzbd while gaming, resumes on exit

## How it works

StreamPilot connects to OBS via WebSocket. **OBS must already be open** before you start StreamPilot.

Typical session:

1. Open OBS (StreamPilot needs it running to connect)
2. Start StreamPilot (`scripts\run.bat` or `python src\streampilot.py start`)
3. Launch your game
4. StreamPilot detects the game, sets your OBS Game Capture source, sets the Twitch category, and starts the stream automatically
5. Exit the game - StreamPilot stops the stream and resumes SABnzbd

If you switch to a different game mid-stream, StreamPilot swaps the capture source and Twitch category without interrupting the stream.

> **Note:** "Application Audio Capture" in OBS is a one-time manual step per new game - add the game exe to that source yourself the first time. StreamPilot only automates the Game Capture source and Twitch category.

## One-time setup

### 1. Install dependencies

```
pip install -r config\requirements.txt
```

### 2. Configure OBS WebSocket

OBS > Tools > WebSocket Server Settings > enable, set port 4455, set a password.

### 3. Create config

```
copy config\config.example.json config\config.json
```

Fill in `config.json` with your OBS password, Twitch credentials, and SABnzbd API key.

### 4. Get Twitch token

```
python src\streampilot.py auth
```

Follow the prompts to generate and save an OAuth token.

### 5. Add your games (while the game is running)

```
python src\streampilot.py config add-game
```

Detects the running game window, searches Twitch for the category, and writes it to config. Repeat for each game.

## Daily use

```
python src\streampilot.py start
```

Or double-click `scripts\run.bat`. Then just open OBS and launch your game - everything else is automatic.

## Commands

| Command | Action |
|---|---|
| `python src\streampilot.py start` | Start polling daemon |
| `python src\streampilot.py status` | Show current game / stream / SABnzbd state |
| `python src\streampilot.py config add-game` | Add a new game (game must be running) |
| `python src\streampilot.py auth` | Set up Twitch OAuth token |

## Config reference

See `config\config.example.json`. Key fields:

- `obs.password` - OBS WebSocket password
- `obs.game_capture_source` - exact name of your Game Capture source in OBS
- `twitch.client_id` / `twitch.oauth_token` - from Twitch developer console + auth flow
- `sabnzbd.api_key` - from SABnzbd > Config > General > API Key
- `games` - map of `exe_name` to `{name, twitch_game_id, obs_window}`

The `obs_window` string format is `Window Title:Window Class:Executable` and is generated automatically by `config add-game`.
