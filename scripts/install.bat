@echo off
title StreamPilot - Install Dependencies
echo Installing StreamPilot dependencies...
cd /d "%~dp0.."
pip install -r config\requirements.txt
echo.
echo Done. You can close this window.
pause
