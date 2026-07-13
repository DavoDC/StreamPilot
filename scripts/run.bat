:: Starts the StreamPilot daemon and opens the live dashboard in your browser - one click.
:: Monitors running processes and auto-manages OBS and Twitch when a known game is detected.
@echo off
title StreamPilot

:: Auto-elevate: OBS requires admin rights for game capture (Marvel Rivals silently fails without it)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process -FilePath wt.exe -ArgumentList 'cmd /k cd /d \"%~dp0..\" && python src\streampilot.py start --dashboard' -Verb RunAs"
    exit /b
)

echo Starting StreamPilot + dashboard...
cd /d "%~dp0.."
python src\streampilot.py start --dashboard
echo.
echo StreamPilot exited.
pause
