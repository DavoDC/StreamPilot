# StreamPilot

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Auto-manages OBS streaming + SABnzbd when you launch a known game.

- Detects game launch via process polling
- Updates OBS Game Capture source to the game's window
- Sets Twitch category to the matching game
- Starts the stream (or swaps game mid-stream)
- Pauses SABnzbd while gaming, resumes on exit

## How it works

1. Start StreamPilot (`scripts\run.bat` or `python src\streampilot.py start`)
2. StreamPilot auto-launches OBS if not already open, then connects via WebSocket
3. Launch your game
4. StreamPilot detects the game, sets your OBS Game Capture source, sets the Twitch category, and starts the stream automatically
5. Exit the game - StreamPilot stops the stream and resumes SABnzbd

If you switch games mid-stream, StreamPilot swaps the capture source and Twitch category without interrupting the stream.

> **Note:** "Application Audio Capture" in OBS is a one-time manual step per new game - add the game exe to that source yourself the first time. StreamPilot only automates Game Capture and Twitch category.

---

## Setup (one-time)

### Step 1 - Install dependencies

```
pip install -r config\requirements.txt
```

### Step 2 - Configure OBS WebSocket

StreamPilot talks to OBS via its built-in WebSocket server.

In OBS: **Tools > WebSocket Server Settings**
- Enable WebSocket server: ON
- Server Port: `4455`
- Enable Authentication: ON
- Set a password and copy it - you will need it in Step 3

StreamPilot will auto-launch OBS at startup if it is not already running.
To enable this, set `obs.exe_path` in `config.json` to your OBS executable path.
Default: `C:\Program Files\obs-studio\bin\64bit\obs64.exe`

Also check that your Game Capture source in OBS is named exactly `Game Capture` - this is what StreamPilot targets. You can rename it or change `obs.game_capture_source` in config to match.

### Step 3 - Create config.json

```
copy config\config.example.json config\config.json
```

Open `config\config.json` and fill in:

| Field | What it is | How to get it |
|---|---|---|
| `obs.password` | OBS WebSocket password | The password you set in Step 2 |
| `obs.exe_path` | Path to obs64.exe | Usually `C:\Program Files\obs-studio\bin\64bit\obs64.exe` |
| `obs.game_capture_source` | Exact name of your Game Capture source in OBS | Check your OBS Sources panel |
| `twitch.client_id` | Your Twitch app ID | See Step 4 below |
| `twitch.oauth_token` | Token proving you can edit your channel | Generated in Step 5 below |
| `sabnzbd.api_key` | SABnzbd API key | SABnzbd > Config > General > API Key |
| `sabnzbd.enabled` | Set to `false` if you don't use SABnzbd | - |

### Step 4 - Get a Twitch Client ID

StreamPilot calls the Twitch API to set your stream category when a game launches. Twitch requires every API caller to have a registered app ID.

1. Go to [dev.twitch.tv/console](https://dev.twitch.tv/console) and log in
2. Click **Register Your Application**
3. Name: anything (e.g. `StreamPilot`)
4. OAuth Redirect URL: `http://localhost`
5. Category: **Other**
6. Click **Create**, then **Manage**
7. Copy the **Client ID** and paste it into `twitch.client_id` in config.json

### Step 5 - Get a Twitch OAuth token

This token gives StreamPilot permission to update YOUR channel's category.

```
python src\streampilot.py auth
```

Follow the prompts. The token is saved to config.json automatically.

### Step 6 - Add your games

Run this while the game is open and in the foreground:

```
python src\streampilot.py config add-game
```

StreamPilot scans running windows, lets you pick the game, searches Twitch for the category, and writes the entry to config. Repeat for each game you want to automate.

---

## Daily use

```
python src\streampilot.py start
```

Or double-click `scripts\run.bat`. Then just launch your game - everything else is automatic.

## Commands

| Command | Action |
|---|---|
| `python src\streampilot.py start` | Start polling daemon |
| `python src\streampilot.py status` | Show current game / stream / SABnzbd state |
| `python src\streampilot.py config add-game` | Add a new game (game must be running) |
| `python src\streampilot.py auth` | Set up Twitch OAuth token |
