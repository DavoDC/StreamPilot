:: Opens the StreamPilot dashboard - a small live status window for the second monitor.
:: Run this alongside run.bat (the dashboard reads status.json; it does not start the daemon).
@echo off
title StreamPilot Dashboard
cd /d "%~dp0.."
python src\streampilot.py dashboard
echo.
echo Dashboard closed.
pause
