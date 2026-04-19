:: One-time setup. Copies config.example.json to config.json if it doesn't exist yet. Open config.json afterwards to fill in your settings.
@echo off
title StreamPilot - Create Config
cd /d "%~dp0..\.."
if exist config\config.json (
    echo config\config.json already exists. Skipping copy.
) else (
    copy config\config.example.json config\config.json
    echo config\config.json created. Open it and fill in your settings.
)
echo.
pause
