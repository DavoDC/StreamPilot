:: Shows the current StreamPilot state - active game, OBS stream status, and SABnzbd status.
@echo off
title StreamPilot - Status
cd /d "%~dp0.."
python src\streampilot.py status
echo.
pause
