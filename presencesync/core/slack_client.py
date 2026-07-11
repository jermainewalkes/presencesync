"""Slack API client: huddle/status reads, status writes, automatic token refresh."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from . import constants, credentials
from .errors import ApiError, NeedsAuth
from .models import SlackProfile, SlackStatus
from .store import SecretStore

log = logging.getLogger(__name__)

_REFRESH_SKEW_SECONDS = 300  # refresh this long before expiry
_AUTH_ERRORS = {"invalid_auth", "not_authed", "token_expired", "token_revoked", "account_inactive"}


class SlackClient:
    def __init__(self, secrets: Optional[SecretStore] = None, settings=None) -> None:
        self.secrets = secrets or SecretStore()
        if settings is None:
            from .store import Settings

            settings = Settings.load()
        self.settings = settings
        self._session = requests.Session()

    # Token state
    def _tokens(self) -> Optional[dict]:
        return self.secrets.get_slack_tokens()

    def is_connected(self) -> bool:
        return self._tokens() is not None

    def has_refresh_token(self) -> bool:
        return bool((self._tokens() or {}).get("refresh_token"))

    @property
    def token_expires_at(self) -> float:
        tokens = self._tokens() or {}
        return float(tokens.get("expires_at", 0) or 0)

    def sign_out(self) -> None:
        self.secrets.clear_slack_tokens()

    def _access_token(self) -> str:
        tokens = self._tokens()
        if not tokens or not tokens.get("access_token"):
            raise NeedsAuth("Slack not connected")
        expires_at = float(tokens.get("expires_at", 0) or 0)
        if tokens.get("refresh_token") and expires_at and time.time() > expires_at - _REFRESH_SKEW_SECONDS:
            tokens = self._refresh(tokens["refresh_token"])
        return tokens["access_token"]

    def _refresh(self, refresh_token: str) -> dict:
        client_id = credentials.slack_client_id(self.settings)
        client_secret = credentials.slack_client_secret(self.secrets)
        if not (client_id and client_secret):
            raise NeedsAuth("Slack client credentials not configured; cannot refresh token")
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        try:
            resp = self._session.post(f"{constants.SLACK_API}/oauth.v2.access", data=data, timeout=10)
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiError(f"Slack token refresh failed: {exc}") from exc
        if not payload.get("ok"):
            raise NeedsAuth(f"Slack token refresh rejected: {payload.get('error')}")
        # Rotation fields may be top-level or under authed_user depending on token type.
        src = payload.get("authed_user") if "authed_user" in payload else payload
        new_access = src.get("access_token")
        if not new_access:
            raise ApiError("Slack token refresh returned no access token")
        tokens = self._tokens() or {}
        tokens["access_token"] = new_access
        if src.get("refresh_token"):
            tokens["refresh_token"] = src["refresh_token"]
        # Always advance expiry — if Slack omits expires_in we still move it forward so
        # we don't try to refresh again on every single call.
        expires_in = src.get("expires_in")
        tokens["expires_at"] = time.time() + int(expires_in if expires_in else 11 * 3600)
        self.secrets.set_slack_tokens(tokens)
        log.info("Refreshed Slack token; next expiry in %ss", expires_in)
        return tokens

    # API helpers
    def _get(self, method: str, params: Optional[dict] = None) -> dict:
        return self._call("get", method, params=params)

    def _post(self, method: str, json_body: Optional[dict] = None) -> dict:
        return self._call("post", method, json_body=json_body)

    def _call(self, verb: str, method: str, params=None, json_body=None) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        try:
            resp = self._session.request(
                verb, f"{constants.SLACK_API}/{method}",
                headers=headers, params=params, json=json_body, timeout=10,
            )
            if resp.status_code == 429:
                retry = resp.headers.get("Retry-After", "")
                raise ApiError(f"Slack {method} rate-limited" + (f"; retry after {retry}s" if retry else ""))
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise ApiError(f"Slack {method} failed: {exc}") from exc
        if not payload.get("ok"):
            error = payload.get("error", "unknown")
            if error in _AUTH_ERRORS:
                raise NeedsAuth(f"Slack auth error: {error}")
            raise ApiError(f"Slack {method} → {error}")
        return payload

    # Presence / status
    def validate_token(self) -> bool:
        return bool(self._post("auth.test").get("ok"))

    def get_profile(self) -> SlackProfile:
        profile = self._get("users.profile.get").get("profile", {})
        return SlackProfile(
            in_huddle=profile.get("huddle_state") == "in_a_huddle",
            status_text=profile.get("status_text", "") or "",
            status_emoji=profile.get("status_emoji", "") or "",
        )

    def set_status(self, status: SlackStatus) -> None:
        self._post(
            "users.profile.set",
            {
                "profile": {
                    "status_text": status.text,
                    "status_emoji": status.emoji,
                    "status_expiration": status.expiration,
                }
            },
        )
