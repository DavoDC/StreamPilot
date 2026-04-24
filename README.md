# StreamPilot

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Auto-manages OBS streaming + SABnzbd when you launch a known game.

- Detects game launch via process polling
- Updates OBS Game Capture source to the game's window
- Sets Twitch category to the matching game
- Starts the stream (or swaps game mid-stream)
- Pauses SABnzbd while gaming, resumes on exit

## How it works

1. Start StreamPilot by running `scripts\run.bat`.
2. StreamPilot auto-launches OBS if not already open, then connects via WebSocket
3. Launch your game
4. StreamPilot detects the game, sets your OBS Game Capture source, sets the Twitch category, and starts the stream automatically
5. StreamPilot automatically monitors SABnzbd and pauses it if it is running to prevent it from affecting network performance in-game.
6. Exit the game - StreamPilot stops the stream and resumes SABnzbd

If you switch games mid-stream, StreamPilot swaps the capture source and Twitch category without interrupting the stream.

> **Note:** "Application Audio Capture" in OBS is a one-time manual step per new game - add the game exe to that source yourself the first time. StreamPilot only automates Game Capture and Twitch category.

---

## Prerequisites

- A Twitch account with **Two-Factor Authentication (2FA) enabled** - required by Twitch when authorising StreamPilot to manage your channel. Enable it at [twitch.tv/settings/security](https://www.twitch.tv/settings/security) under "Two-Factor Authentication"
- [Python 3.8+](https://www.python.org/downloads/)
- [OBS Studio](https://obsproject.com/download)

## Setup (one-time)

### Step 1 - Install dependencies

Double-click `scripts\setup\install.bat`.

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

Copy `config\config.example.json` to `config\config.json`, then open it and fill in:

| Field | What it is | How to get it |
|---|---|---|
| `obs.password` | OBS WebSocket password | The password you set in Step 2 |
| `obs.game_capture_source` | Exact name of your Game Capture source in OBS | Check your OBS Sources panel |
| `obs.exe_path` | Path to obs64.exe | Usually `C:\Program Files\obs-studio\bin\64bit\obs64.exe` |
| `twitch.client_id` | Client ID paired with your OAuth token | See Step 4 below |
| `twitch.oauth_token` | Token proving you can edit your channel | See Step 4 below |
| `sabnzbd.api_key` | SABnzbd API key | SABnzbd > Config > General > API Key |
| `sabnzbd.enabled` | Set to `false` if you don't use SABnzbd | - |

### Step 4 - Get a Twitch OAuth token and Client ID

This token gives StreamPilot permission to update your channel's category. The token generator also provides the Client ID that must match it.

1. Go to [twitchtokengenerator.com](https://twitchtokengenerator.com)
2. Click **Custom Scope Token**
3. Enable scope: `channel:manage:broadcast`
4. Click **Generate Token** and authorise with your Twitch account
5. Copy the **Access Token** into `twitch.oauth_token` in config.json
6. Copy the **Client ID** shown on that same page into `twitch.client_id` in config.json - this Client ID is paired with your token and must match it exactly

### Step 5 - Add your games

Launch the game you want to add, then double-click `scripts\setup\add-game.bat`. The game does not need to be in the foreground - it just needs to be running.

StreamPilot scans running windows, lets you pick the game, searches Twitch for the category, and writes the entry to config. Repeat for each game you want to automate.

---

## Usage

Double-click `scripts\run.bat`. Then just launch your game - everything else is automatic.