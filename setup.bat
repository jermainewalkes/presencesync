@echo off
rem PresenceSync setup for Windows. Double-click to install and launch.
rem Requires Python 3.11+ from python.org (the "py" launcher).

setlocal
cd /d "%~dp0"

echo ------------------------------------------
echo   PresenceSync setup
echo ------------------------------------------

where py >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install it from https://www.python.org/downloads/windows/
    echo then run this file again. Tick "Add python.exe to PATH" during install.
    start https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Python 3.11 or newer is required. Please update from python.org.
    pause
    exit /b 1
)

if not exist venv (
    echo Creating the virtual environment...
    py -3 -m venv venv
)

echo Installing dependencies...
venv\Scripts\python -m pip install --upgrade pip --quiet
venv\Scripts\pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo Dependency install failed. Check your network connection and retry.
    pause
    exit /b 1
)

echo.
echo Setup complete. Launching PresenceSync - look for the tray icon.
echo First run: open Settings from the tray icon, enter your IDs (or drop in
echo an org-config.json first), Save, then Connect Microsoft and Connect Slack.
echo.
start "" venv\Scripts\pythonw.exe main.py --app
exit /b 0
