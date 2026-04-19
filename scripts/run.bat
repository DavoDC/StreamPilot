:: Starts the StreamPilot daemon - monitors running processes and auto-manages OBS and Twitch when a known game is detected.
@echo off
title StreamPilot
echo Starting StreamPilot...
cd /d "%~dp0.."
python src\streampilot.py start
echo.
echo StreamPilot exited.
pause
