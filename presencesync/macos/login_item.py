"""Start-at-login via a per-user LaunchAgent."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys

from ..core import constants

_LAUNCH_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
_PLIST_PATH = os.path.join(_LAUNCH_AGENTS_DIR, f"{constants.BUNDLE_ID}.plist")


def _program_arguments() -> list[str]:
    if getattr(sys, "frozen", False):  # packaged .app
        return [sys.executable]
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [sys.executable, os.path.join(project_root, "main.py"), "--app"]


def is_enabled() -> bool:
    return os.path.exists(_PLIST_PATH)


def enable() -> None:
    os.makedirs(_LAUNCH_AGENTS_DIR, exist_ok=True)
    os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
    plist = {
        "Label": constants.BUNDLE_ID,
        "ProgramArguments": _program_arguments(),
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "StandardOutPath": constants.LOG_PATH,
        "StandardErrorPath": constants.LOG_PATH,
    }
    with open(_PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "load", "-w", _PLIST_PATH], check=False)


def disable() -> None:
    subprocess.run(["launchctl", "unload", "-w", _PLIST_PATH], check=False)
    if os.path.exists(_PLIST_PATH):
        os.remove(_PLIST_PATH)
