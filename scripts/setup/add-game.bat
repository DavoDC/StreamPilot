:: Wizard to add a new game. Have the game running first (does not need to be in the foreground). Detects running windows, looks up the Twitch category, and saves the entry to config.json.
@echo off
title StreamPilot - Add Game
echo Make sure your game is running, then press any key to continue.
echo.
pause
cd /d "%~dp0..\.."
python src\streampilot.py config add-game
echo.
echo Done. You can close this window.
pause
