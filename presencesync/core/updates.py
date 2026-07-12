"""Self-update: daily release check against GitHub, one-click git pull + restart.

The check asks GitHub for the latest release tag; the update itself is a
fast-forward `git pull` from the checkout's own origin, so org clones and the
private-remote development checkout both work unchanged.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from typing import NamedTuple, Optional

import requests

from .errors import UpdateError

log = logging.getLogger(__name__)

GITHUB_REPO = "jermainewalkes/presencesync"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
CHECK_INTERVAL_SECONDS = 24 * 3600


class Release(NamedTuple):
    tag: str
    url: str


def _version_tuple(version: str) -> tuple:
    parts = []
    for piece in version.lstrip("vV").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(tag: str, current: Optional[str] = None) -> bool:
    if not tag:
        return False
    if current is None:
        from .. import __version__ as current
    try:
        return _version_tuple(tag) > _version_tuple(current)
    except ValueError:
        return False


def latest_release() -> Optional[Release]:
    try:
        resp = requests.get(
            LATEST_RELEASE_API, headers={"Accept": "application/vnd.github+json"}, timeout=10
        )
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.info("update check skipped: %s", exc)
        return None
    tag = data.get("tag_name")
    if not tag:
        return None
    return Release(tag, data.get("html_url") or RELEASES_URL)


def check(settings, force: bool = False) -> Optional[Release]:
    """Return a newer Release if one is known, hitting the network at most daily.

    A previously seen tag (persisted in settings) is honoured immediately so the
    menu item reappears after a restart without waiting for the next check.
    """
    if not (force or settings.auto_check_updates):
        return None
    if settings.last_update_notified and is_newer(settings.last_update_notified):
        return Release(settings.last_update_notified, RELEASES_URL)
    now = time.time()
    if not force and now - settings.last_update_check < CHECK_INTERVAL_SECONDS:
        return None
    settings.last_update_check = now
    settings.save()
    release = latest_release()
    if release and is_newer(release.tag):
        return release
    return None


# Applying
def repo_root() -> Optional[str]:
    path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for _ in range(3):
        if os.path.isdir(os.path.join(path, ".git")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


def can_apply() -> bool:
    return repo_root() is not None


def _run(args: list, timeout: int) -> str:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"{args[0]} failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[-300:]
        raise UpdateError(f"{' '.join(args[:3])} failed: {detail}")
    return proc.stdout


def apply_update() -> None:
    """Fast-forward the checkout and reinstall dependencies. Raises UpdateError."""
    root = repo_root()
    if root is None:
        raise UpdateError("Not a git checkout - download the update from GitHub")
    status = _run(["git", "-C", root, "status", "--porcelain"], timeout=30)
    dirty = [line for line in status.splitlines() if line.strip() and not line.startswith("??")]
    if dirty:
        raise UpdateError("Local changes present - update manually with git pull")
    _run(["git", "-C", root, "pull", "--ff-only"], timeout=120)
    req = os.path.join(root, "requirements.txt")
    if os.path.exists(req):
        _run([sys.executable, "-m", "pip", "install", "-r", req], timeout=600)


def restart_app() -> None:
    """Relaunch the app on the updated code. Releases the single-instance lock first."""
    from . import single_instance

    root = repo_root()
    main_py = os.path.join(root or os.getcwd(), "main.py")
    args = [sys.executable, main_py, "--app"]
    single_instance.release()
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        subprocess.Popen(args, creationflags=flags, close_fds=True)
        os._exit(0)
    os.execv(sys.executable, args)
