@echo off
title StreamPilot Tests
echo Running StreamPilot tests...
cd /d "%~dp0.."
python -m pytest tests/ -v
echo.
pause
