"""Cross-platform single-instance lock backed by an exclusive file lock."""

from __future__ import annotations

import os

from . import constants

_lock_file = None


def acquire() -> bool:
    """Try to take the app-wide lock. Returns False if another instance holds it."""
    global _lock_file
    os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
    _lock_file = open(os.path.join(constants.APP_SUPPORT_DIR, "presencesync.lock"), "w")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False
