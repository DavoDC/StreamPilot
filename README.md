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

- A Twitch account with **Two-Factor Authentication (2FA) enabled** - required by Twitch before you can register a developer application. Enable it at [twitch.tv/settings/security](https://www.twitch.tv/settings/security) under "Two-Factor Authentication"
- [Python 3.8+](https://www.python.org/downloads/)
- [OBS Studio](https://obsproject.com/download)

## Setup (one-time)

### Step 1 - Install dependencies

Double-click `scripts\install.bat`.

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

Double-click `scripts\setup-config.bat`. Then open `config\config.json` and fill in:

| Field | What it is | How to get it |
|---|---|---|
| `obs.password` | OBS WebSocket password | The password you set in Step 2 |
| `obs.game_capture_source` | Exact name of your Game Capture source in OBS | Check your OBS Sources panel |
| `obs.exe_path` | Path to obs64.exe | Usually `C:\Program Files\obs-studio\bin\64bit\obs64.exe` |
| `twitch.client_id` | Your Twitch app ID | See Step 4 below |
| `twitch.oauth_token` | Token proving you can edit your channel | Generated in Step 5 below |
| `sabnzbd.api_key` | SABnzbd API key | SABnzbd > Config > General > API Key |
| `sabnzbd.enabled` | Set to `false` if you don't use SABnzbd | - |

### Step 4 - Get a Twitch Client ID

StreamPilot calls the Twitch API to set your stream category when a game launches. Twitch requires every API caller to have a registered app ID.

1. Go to [dev.twitch.tv/console](https://dev.twitch.tv/console) and log in
2. Click **Register Your Application**
3. Name: anything (e.g. `Davo_StreamPilot`)
4. OAuth Redirect URL: `http://localhost`
5. Category: **Other**
6. Client Type: **Public** - StreamPilot is a native desktop app; secrets stored in local config files cannot be kept confidential, so Public is the correct type per the OAuth spec
7. Click **Create**, then **Manage**
8. Copy the **Client ID** and paste it into `twitch.client_id` in config.json

### Step 5 - Get a Twitch OAuth token

This token gives StreamPilot permission to update YOUR channel's category.

1. Go to [twitchtokengenerator.com](https://twitchtokengenerator.com)
2. Click **Custom Scope Token**
3. Enable scope: `channel:manage:broadcast`
4. Click **Generate Token** and authorise with your Twitch account
5. Copy the **Access Token**
6. Open `config\config.json` and paste it as the value for `twitch.oauth_token`

### Step 6 - Add your games

Launch the game you want to add and make sure it is open and in the foreground, then double-click `scripts\add-game.bat`.

StreamPilot scans running windows, lets you pick the game, searches Twitch for the category, and writes the entry to config. Repeat for each game you want to automate.

---

## Usage

Double-click `scripts\run.bat`. Then just launch your game - everything else is automatic.