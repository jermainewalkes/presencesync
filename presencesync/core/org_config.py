"""Seed app credentials from an org-config.json distributed by an org admin.

Checked on startup: values fill only fields the user has not already set, so a
colleague can drop the file next to the app and just click Connect.
"""

from __future__ import annotations

import json
import logging
import os

from . import constants

log = logging.getLogger(__name__)

_FILENAME = "org-config.json"


def _candidate_paths() -> list[str]:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [os.path.join(repo_root, _FILENAME), os.path.join(constants.APP_SUPPORT_DIR, _FILENAME)]


def seed_if_present(settings, secrets) -> bool:
    """Fill empty credential fields from the first org-config found. Returns True if
    anything was seeded."""
    for path in _candidate_paths():
        if os.path.exists(path):
            break
    else:
        return False

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", path, exc)
        return False

    changed = False
    for field in ("ms_tenant_id", "ms_client_id", "slack_client_id"):
        value = (data.get(field) or "").strip()
        if value and not getattr(settings, field):
            setattr(settings, field, value)
            changed = True

    secret = (data.get("slack_client_secret") or "").strip()
    if secret and not secrets.get_slack_client_secret():
        secrets.set_slack_client_secret(secret)
        changed = True

    if changed:
        settings.save()
        log.info("seeded credentials from %s", path)
    return changed
