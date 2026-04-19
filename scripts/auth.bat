@echo off
title StreamPilot - Twitch Auth
echo Setting up Twitch OAuth token...
cd /d "%~dp0.."
python src\streampilot.py auth
echo.
echo Auth complete. You can close this window.
pause
