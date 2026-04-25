:: Runs the full test suite using pytest. Use this to verify nothing is broken after making changes.
@echo off
title StreamPilot Tests
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
echo Running StreamPilot tests...
python -m pytest tests/ -v --log-file=data\logs\run-tests.log --log-file-level=INFO
echo.
pause
