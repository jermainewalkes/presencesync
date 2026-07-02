"""Microsoft Graph client: MSAL auth with encrypted cache, presence reads/writes.

Preferred presence is sticky and must be cleared explicitly when no longer wanted.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

import msal
import requests

from . import constants, credentials
from .errors import ApiError, NeedsAuth
from .models import TeamsPresence

log = logging.getLogger(__name__)


def _build_cache() -> msal.SerializableTokenCache:
    """A Keychain-encrypted, cross-process token cache, falling back to an in-memory
    cache if msal-extensions / Keychain isn't available (e.g. odd CI)."""
    os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
    location = os.path.join(constants.APP_SUPPORT_DIR, "msal.cache")
    try:
        from msal_extensions import PersistedTokenCache, build_encrypted_persistence

        return PersistedTokenCache(build_encrypted_persistence(location=location))
    except Exception as exc:  # pragma: no cover - environment dependent
        log.warning("Keychain-backed MSAL cache unavailable (%s); using in-memory cache", exc)
        return msal.SerializableTokenCache()


class TeamsClient:
    def __init__(self, settings=None) -> None:
        from .store import Settings

        self.settings = settings or Settings.load()
        client_id = credentials.ms_client_id(self.settings)
        if client_id:
            self._app = msal.PublicClientApplication(
                client_id=client_id,
                authority=credentials.ms_authority(self.settings),
                token_cache=_build_cache(),
            )
        else:
            self._app = None
        self.token_expires_at: float = 0.0

    # Auth
    def _account(self):
        if self._app is None:
            return None
        accounts = self._app.get_accounts()
        return accounts[0] if accounts else None

    def is_connected(self) -> bool:
        return self._account() is not None

    def acquire_token(self, allow_interactive: bool = False) -> str:
        if self._app is None:
            raise NeedsAuth("Microsoft app not configured - add your Tenant ID and Client ID in Settings")
        account = self._account()
        result = None
        if account is not None:
            result = self._app.acquire_token_silent(constants.MS_SCOPES, account=account)
        if not result and allow_interactive:
            result = self._app.acquire_token_interactive(
                scopes=constants.MS_SCOPES, prompt="select_account"
            )
        if not result or "access_token" not in result:
            err = (result or {}).get("error_description", "no cached Microsoft account")
            raise NeedsAuth(f"Microsoft sign-in required: {err}")
        self.token_expires_at = time.time() + int(result.get("expires_in", 0))
        return result["access_token"]

    def connect(self) -> None:
        """Interactive browser sign-in (first connect / reconnect)."""
        self.acquire_token(allow_interactive=True)

    def sign_out(self) -> None:
        account = self._account()
        if account is not None:
            self._app.remove_account(account)
        self.token_expires_at = 0.0

    # HTTP helpers
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.acquire_token(allow_interactive=False)}",
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: Optional[dict] = None) -> None:
        try:
            resp = requests.post(
                f"{constants.GRAPH_BASE}{path}", headers=self._headers(), json=body or {}, timeout=10
            )
        except requests.RequestException as exc:
            raise ApiError(f"Graph request failed: {exc}") from exc
        if resp.status_code == 401:
            raise NeedsAuth("Microsoft token rejected (401)")
        if not resp.ok:
            raise ApiError(f"Graph {path} → {resp.status_code}: {resp.text[:200]}")

    # Presence
    def get_presence(self) -> TeamsPresence:
        try:
            resp = requests.get(
                f"{constants.GRAPH_BASE}/me/presence", headers=self._headers(), timeout=10
            )
        except requests.RequestException as exc:
            raise ApiError(f"Graph presence request failed: {exc}") from exc
        if resp.status_code == 401:
            raise NeedsAuth("Microsoft token rejected (401)")
        if not resp.ok:
            raise ApiError(f"Graph /me/presence → {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        return TeamsPresence(
            availability=data.get("availability", "Unknown"),
            activity=data.get("activity", "Unknown"),
        )

    def set_preferred_presence(
        self,
        availability: str = constants.HUDDLE_TEAMS_AVAILABILITY,
        activity: str = constants.HUDDLE_TEAMS_ACTIVITY,
        expiration: str = constants.HUDDLE_PRESENCE_EXPIRATION,
    ) -> None:
        self._post(
            "/me/presence/setUserPreferredPresence",
            {"availability": availability, "activity": activity, "expirationDuration": expiration},
        )

    def clear_preferred_presence(self) -> None:
        self._post("/me/presence/clearUserPreferredPresence")

    def set_status_message(self, text: str) -> None:
        self._post(
            "/me/presence/setStatusMessage",
            {"statusMessage": {"message": {"content": text, "contentType": "text"}}},
        )

    def clear_status_message(self) -> None:
        self.set_status_message("")
