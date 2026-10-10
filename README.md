# StreamPilot

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Launch a game and you are live. One click starts StreamPilot, and from then on it runs your whole stream: it opens OBS, points it at your game, sets your Twitch category, title and tags, starts the stream, and keeps your downloads from choking your upload. Close the game and it ends the stream and tidies up. You never touch OBS or Twitch settings again.

## Why you will want it

- **One click, then forget it.** Start it once; every game after that is automatic.
- **Everything handled for you.** Right window captured, right Twitch category, a fresh title and tags for each game, stream started, SABnzbd paused so downloads never slow your stream.
- **It keeps fixing itself.** Every couple of seconds it checks that OBS is connected, the right window is captured, the stream is up and downloads are still paused, and puts anything that drifted back.
- **Know it is all good at a glance.** A live dashboard on your second screen shows OBS, Twitch and SABnzbd in one place, and the browser tab title and icon change colour with the status.
- **Safe to stream.** It never broadcasts a non-game window, and private audio can never reach the stream.
- **Light and local.** It runs entirely on your own PC, with no cloud service of its own and no heavy dependencies.

## Dashboard

![StreamPilot dashboard showing OBS, Twitch and SABnzbd status](assets/dashboard.png)

## How it works

1. Run `scripts\run.bat`. It starts StreamPilot, launches OBS if needed, and opens the live dashboard in your browser.
2. Launch your game. StreamPilot sets the OBS capture, the Twitch category, title and tags, and starts the stream.
3. It pauses SABnzbd for the session so downloads do not hurt your connection mid-game.
4. Close the game. The stream ends and SABnzbd resumes. Each game gets its own stream, so the next game starts a fresh one.
5. Done for the night? Click **Quit** on the dashboard and confirm. It stops the stream, resumes SABnzbd and closes itself. `run.bat` has no console window, so this is the only way to shut it down other than Task Manager.

## Private audio can never reach the stream

Anything you are not actively playing stays off the stream, every second you are live, without you having to mute it, check a source list, or trust a setup from six months ago.

StreamPilot owns OBS's "Application Audio Output Capture" source directly: when your game launches, its exe becomes the *only* entry in that source's capture list, and everything else is removed. Every heartbeat while you stream, it re-checks the live list against that one allowed exe. If anything unexpected appears, it force-stops the stream immediately instead of just logging a warning. There is no allow-list to maintain and no wide list of every game you have ever added sitting in the capture source waiting to leak: exactly one exe, the one you are playing now.

---

## Prerequisites

- A Twitch account with **Two-Factor Authentication (2FA) enabled** - required by Twitch when authorising StreamPilot to manage your channel. Enable it at [twitch.tv/settings/security](https://www.twitch.tv/settings/security) under "Two-Factor Authentication"
- [Python 3.8+](https://www.python.org/downloads/)
- [OBS Studio](https://obsproject.com/download)

## Setup (one-time)

### Step 1 - Install dependencies

Double-click `scripts\setup\install-dependencies.bat`.

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