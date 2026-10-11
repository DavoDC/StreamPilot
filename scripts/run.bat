:: One-click launcher (thin wrapper). All logic lives in src\launcher.py and is tested; this only elevates.
:: 1. preflight (python, imports, config, port) in this visible console; a failure holds the window open with the reason.
:: 2. self-elevate (OBS game capture needs admin rights; the replace step must see an old elevated instance too).
:: 3. `streampilot.py launch` replaces any StreamPilot on port 8765 by PORT OWNER (never by command line), starts the
::    windowless pythonw child (hot reload on, dashboard tab opens) and returns once it answers.
:: Restarting StreamPilot never ends the OBS stream; the new process adopts a live session.
:: Usage: run.bat [--no-browser] [--no-watch] [--port N]     Verbs: python src\streampilot.py launch|stop|check|preflight
@echo off
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
>>data\logs\launch-breadcrumb.log echo %DATE% %TIME% run.bat args=[%*]
if "%1"=="--elevated" goto launch
where python >nul 2>nul || goto nopython
python src\streampilot.py preflight || goto failed

net session >nul 2>&1
if %errorlevel% equ 0 goto launch
powershell -NoProfile -WindowStyle Hidden -Command "Start-Process -FilePath '%~f0' -ArgumentList '--elevated %*' -WorkingDirectory '%cd%' -Verb RunAs -WindowStyle Hidden"
exit /b 0

:launch
set "ARGS=%*"
set "ARGS=%ARGS:--elevated=%"
python src\streampilot.py launch %ARGS%
exit /b %errorlevel%

:nopython
echo.
echo [FAILED] python is not on PATH. Install Python 3.11+ and tick "Add to PATH", then run this again.
goto hold

:failed
echo.
echo [FAILED] StreamPilot was not started. Fix the problem above, then run this again.

:hold
cmd /k
exit /b 2
