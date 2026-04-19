@echo off
title StreamPilot - Status
cd /d "%~dp0.."
python src\streampilot.py status
echo.
pause
