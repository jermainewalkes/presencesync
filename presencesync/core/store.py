"""Persistence: user settings (a small JSON in Application Support) and secrets
(Slack OAuth tokens) in the macOS Keychain. Nothing sensitive is written to disk.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

import keyring

from . import constants
from .sync import SyncSettings
# Settings — non-secret, user-editable only through the app UI.
@dataclass
class Settings:
    teams_to_slack: bool = True
    slack_to_teams: bool = True
    paused: bool = False
    start_at_login: bool = False
    poll_interval_seconds: int = constants.POLL_INTERVAL_SECONDS
    # App credentials set via the Settings window (override the baked-in defaults).
    # Non-secret values live here; the Slack client secret lives in the Keychain.
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    slack_client_id: str = ""
    # Custom Slack status per category + the huddle message (empty/None = defaults).
    status_map: dict = None  # type: ignore[assignment]
    huddle_message: str = ""

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(constants.SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
        tmp = constants.SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, constants.SETTINGS_PATH)

    def to_sync_settings(self) -> SyncSettings:
        overrides = self.status_map or {}
        mapping = {}
        for cat in constants.STATUS_CATEGORIES:
            override = overrides.get(cat.key, {})
            text = override.get("text", cat.text)
            emoji = override.get("emoji", cat.emoji)
            for activity in cat.activities:
                mapping[activity] = {"text": text, "emoji": emoji}
        return SyncSettings(
            teams_to_slack=self.teams_to_slack,
            slack_to_teams=self.slack_to_teams,
            teams_to_slack_map=mapping,
        )
# Secrets — Slack OAuth tokens in the Keychain (service = bundle id).
_SLACK_ACCOUNT = "slack_oauth"
_SLACK_SECRET_ACCOUNT = "slack_client_secret"


class SecretStore:
    """Thin wrapper over `keyring` storing one JSON blob per service account."""

    def __init__(self, service: str = constants.BUNDLE_ID) -> None:
        self.service = service

    def get_slack_tokens(self) -> dict | None:
        raw = keyring.get_password(self.service, _SLACK_ACCOUNT)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None

    def set_slack_tokens(self, tokens: dict) -> None:
        keyring.set_password(self.service, _SLACK_ACCOUNT, json.dumps(tokens))

    def clear_slack_tokens(self) -> None:
        try:
            keyring.delete_password(self.service, _SLACK_ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            pass

    # Slack app client secret (set via the Settings window)
    def get_slack_client_secret(self) -> str:
        return keyring.get_password(self.service, _SLACK_SECRET_ACCOUNT) or ""

    def set_slack_client_secret(self, secret: str) -> None:
        keyring.set_password(self.service, _SLACK_SECRET_ACCOUNT, secret)

    def clear_slack_client_secret(self) -> None:
        try:
            keyring.delete_password(self.service, _SLACK_SECRET_ACCOUNT)
        except keyring.errors.PasswordDeleteError:
            pass
