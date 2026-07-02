#!/bin/bash
# Double-click this in Finder to set up and launch PresenceSync.
# It finds (or installs) Python, builds the venv, installs all dependencies,
# helps you paste your Slack credentials, signs you in, and starts the app.
#
# First time after AirDrop: if macOS blocks it, right-click → Open.

set -euo pipefail
cd "$(dirname "$0")"

echo "──────────────────────────────────────────"
echo "  PresenceSync setup"
echo "──────────────────────────────────────────"

# 1. Find a suitable Python (>= 3.11), preferring 3.13.
pyver_ok() { "$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; }
PY=""
for c in python3.13 python3.12 python3.11 \
         /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 \
         /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
         python3; do
  if command -v "$c" >/dev/null 2>&1 && pyver_ok "$c"; then PY="$c"; break; fi
done

if [ -z "$PY" ]; then
  echo "No suitable Python found."
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Python 3.13 via Homebrew (this can take a minute)…"
    brew install python@3.13
    PY="$(brew --prefix)/bin/python3.13"
  else
    echo "Please install Python from python.org (the macOS 64-bit universal2 installer),"
    echo "then double-click this file again. Opening the download page now…"
    open "https://www.python.org/downloads/macos/"
    read -r -p "Press Return to close." _
    exit 1
  fi
fi
echo "Using $("$PY" --version) ($PY)"

# 2. Virtual environment + dependencies.
echo "Creating the virtual environment…"
"$PY" -m venv venv
echo "Installing dependencies (downloading Apple-Silicon wheels)…"
./venv/bin/python -m pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt

# 3. Launch — credentials and sign-in are done in the app's Settings window.
echo
echo "Setup complete. Launching PresenceSync — look for the icon in the menu bar."
echo
echo "First run: click the menu-bar icon -> Settings... -> paste your Slack Client ID"
echo "and Secret -> Save, then Connect Microsoft and Connect Slack."
echo
echo "To start it again later:  ./venv/bin/python main.py --app"
exec ./venv/bin/python main.py --app
