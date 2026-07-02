"""Start-at-login via the per-user Run registry key."""

from __future__ import annotations

import os
import sys
import winreg

from ..core import constants

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = constants.APP_NAME


def _command() -> str:
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return f'"{pythonw}" "{os.path.join(root, "main.py")}" --app'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except OSError:
        return False


def enable() -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except OSError:
        pass
