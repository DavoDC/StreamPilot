:: Starts the StreamPilot daemon AND opens the live dashboard in your browser - one click.
:: Same as run.bat, but also launches the dashboard. Use run.bat instead if you
:: don't want a browser tab opened every time (e.g. it's already pinned open).
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
