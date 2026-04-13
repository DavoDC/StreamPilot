@echo off
title StreamPilot
echo Starting StreamPilot...
cd /d "%~dp0.."
python src\streampilot.py start
echo.
echo StreamPilot exited.
pause
