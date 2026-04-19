:: One-time setup. Installs all Python dependencies from config\requirements.txt via pip.
@echo off
title StreamPilot - Install Dependencies
echo Installing StreamPilot dependencies...
cd /d "%~dp0..\.."
pip install -r config\requirements.txt
echo.
echo Done. You can close this window.
pause
