:: One-click launcher. Elevates for OBS game capture, kills any previously running
:: StreamPilot instance (avoids stacking up duplicates across dev restarts - the kill step
:: must run elevated too, otherwise it can't see/close a previous elevated instance), then
:: starts the daemon + dashboard via pythonw.exe so no console/terminal window appears.
:: Dashboard opens at http://localhost:8765/. Logs still go to data\logs\ regardless.
:: --watch is on by default: any src/*.py edit self-restarts the process within ~1s
:: and the open dashboard tab reloads itself - lets David improve the program and see
:: changes live while streaming, without disrupting the actual OBS stream (see CLAUDE.md
:: "Dev mode: hot-reload (--watch)"). Restarting doesn't stop OBS - separate process.
@echo off
cd /d "%~dp0.."

:: Auto-elevate: OBS requires admin rights for game capture (Marvel Rivals silently fails without it)
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%cd%' -Verb RunAs -WindowStyle Hidden"
    exit /b
)

powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'streampilot\.py' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

start "" /min pythonw.exe src\streampilot.py start --dashboard --watch
