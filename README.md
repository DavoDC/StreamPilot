# StreamPilot

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/G2G31WKOCN)

Launch a game and you are live. One click starts StreamPilot, and from then on it runs your whole stream: it opens OBS, points it at your game, sets your Twitch category, title and tags, starts the stream, and keeps your downloads from choking your upload. Close the game and it ends the stream and tidies up. You never touch OBS or Twitch settings again.

https://github.com/user-attachments/assets/f252d147-f5b1-4a5c-a0dd-580a6ae9bed9

## Why you will want it

- **One click, then forget it.** Start it once; every game after that is automatic.
- **Everything handled for you.** Right window captured, right Twitch category, a fresh title and tags for each game, stream started, SABnzbd paused so downloads never slow your stream.
- **It keeps fixing itself.** Every couple of seconds it checks that OBS is connected, the right window is captured, the stream is up and downloads are still paused, and puts anything that drifted back.
- **Know it is all good at a glance.** A live dashboard on your second screen shows OBS, Twitch and SABnzbd in one place, and the browser tab title changes with the status and the tab and tray icon show the app icon with a small status badge.
- **Safe to stream.** It never broadcasts a non-game window, and private audio can never reach the stream.
- **Light and local.** It runs entirely on your own PC, with no cloud service of its own and no heavy dependencies.

## Dashboard

![StreamPilot dashboard showing OBS, Twitch and SABnzbd status](assets/dashboard.png)

## How it works

Start it once and it works in the background. Double-click `scriptsun.bat`: it starts StreamPilot, launches OBS if needed and opens the live dashboard in your browser. From then on it watches for your games.

- **When you launch a game:** it sets the OBS capture, the Twitch category, title and tags, and starts the stream. Each game gets its own stream, so the next game starts a fresh one.
- **While you play:** SABnzbd stays paused so downloads do not hurt your connection mid-game. This is not a setup step. It happens on its own for every session, and if something drifts (OBS drops, the wrong window, downloads resumed) it is put back within seconds. With no game running, SABnzbd runs freely.
- **When you close the game:** the stream ends and SABnzbd resumes.
- **Done for the night?** Click **Quit** on the dashboard and confirm. It stops the stream, resumes SABnzbd and closes itself. `run.bat` has no console window, so this is the only way to shut it down other than Task Manager.

## Private audio can never reach the stream

Anything you are not actively playing stays off the stream, every second you are live, without you having to mute it, check a source list, or trust a setup from six months ago.

StreamPilot owns OBS's "Application Audio Output Capture" source directly: when your game launches, its exe becomes the *only* entry in that source's capture list, and everything else is removed. Every heartbeat while you stream, it re-checks the live list against that one allowed exe. If anything unexpected appears, it force-stops the stream immediately instead of just logging a warning. There is no allow-list to maintain and no wide list of every game you have ever added sitting in the capture source waiting to leak: exactly one exe, the one you are playing now.

---

## Prerequisites

- A Twitch account with **Two-Factor Authentication (2FA) enabled** - required by Twitch when authorising StreamPilot to manage your channel. Enable it at [twitch.tv/settings/security](https://www.twitch.tv/settings/security) under "Two-Factor Authentication"
- [Python 3.11+](https://www.python.org/downloads/)
- [OBS Studio](https://obsproject.com/download)

## Get started

One-time setup takes five short steps: see [docs/SETUP.md](docs/SETUP.md). After that, double-click `scriptsun.bat` and launch your game.
