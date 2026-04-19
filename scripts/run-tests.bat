:: Runs the full test suite using pytest. Use this to verify nothing is broken after making changes.
@echo off
title StreamPilot Tests
echo Running StreamPilot tests...
cd /d "%~dp0.."
python -m pytest tests/ -v
echo.
pause
