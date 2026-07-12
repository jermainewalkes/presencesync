"""Cross-platform single-instance lock backed by an exclusive file lock."""

from __future__ import annotations

import os

from . import constants

_lock_file = None


def acquire() -> bool:
    """Try to take the app-wide lock. Returns False if another instance holds it."""
    global _lock_file
    try:
        os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
        _lock_file = open(os.path.join(constants.APP_SUPPORT_DIR, "presencesync.lock"), "a")
        _lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def release() -> None:
    """Drop the lock (used before relaunching after a self-update)."""
    global _lock_file
    if _lock_file is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            _lock_file.seek(0)
            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file, fcntl.LOCK_UN)
        _lock_file.close()
    except OSError:
        pass
    _lock_file = None
