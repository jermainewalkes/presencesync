"""Slack OAuth: open the browser, capture the redirect on a localhost port, and
exchange the code for a (rotating) user token. Blocking — callers in the GUI run it
on a background thread.
"""

from __future__ import annotations

import http.server
import logging
import secrets as _secrets
import time
import urllib.parse
import webbrowser

import requests

from . import constants, credentials
from .errors import ApiError, NeedsAuth
from .store import SecretStore

log = logging.getLogger(__name__)

_SUCCESS_HTML = (
    "<html><body style='font-family:-apple-system,Helvetica,sans-serif;"
    "padding:3rem;text-align:center;color:#1d1d1f'>"
    "<h2>PresenceSync connected ✓</h2>"
    "<p>You can close this window and return to the app.</p></body></html>"
)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server API)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = qs.get("code", [None])[0]
        self.server.auth_state = qs.get("state", [None])[0]
        self.server.auth_error = qs.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_SUCCESS_HTML.encode("utf-8"))

    def log_message(self, *args):  # silence default stderr logging
        pass


def connect_slack(secrets: SecretStore | None = None, settings=None, timeout: int = 180) -> dict:
    """Run the full browser OAuth dance and persist the resulting tokens."""
    secrets = secrets or SecretStore()
    if settings is None:
        from .store import Settings

        settings = Settings.load()
    client_id = credentials.slack_client_id(settings)
    client_secret = credentials.slack_client_secret(secrets)
    if not (client_id and client_secret):
        raise NeedsAuth(
            "Slack client id/secret not configured — add them in Settings… "
            "(or set PRESENCESYNC_SLACK_CLIENT_ID/SECRET)."
        )

    state = _secrets.token_urlsafe(16)
    authorize_url = constants.SLACK_AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": client_id,
            "user_scope": ",".join(constants.SLACK_USER_SCOPES),
            "redirect_uri": constants.SLACK_REDIRECT_URI,
            "state": state,
        }
    )

    try:
        server = http.server.HTTPServer(("127.0.0.1", constants.SLACK_REDIRECT_PORT), _CallbackHandler)
    except OSError as exc:
        raise ApiError(f"Could not start local OAuth listener on port {constants.SLACK_REDIRECT_PORT}: {exc}") from exc
    server.auth_code = server.auth_state = server.auth_error = None
    server.timeout = 1

    webbrowser.open(authorize_url)
    log.info("Opened browser for Slack authorization")
    deadline = time.time() + timeout
    try:
        while server.auth_code is None and server.auth_error is None and time.time() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    if server.auth_error:
        raise NeedsAuth(f"Slack authorization denied: {server.auth_error}")
    if server.auth_code is None:
        raise NeedsAuth("Slack authorization timed out")
    if server.auth_state != state:
        raise NeedsAuth("Slack authorization state mismatch (possible CSRF)")

    try:
        resp = requests.post(
            f"{constants.SLACK_API}/oauth.v2.access",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": server.auth_code,
                "redirect_uri": constants.SLACK_REDIRECT_URI,
            },
            timeout=10,
        )
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ApiError(f"Slack token exchange failed: {exc}") from exc

    if not payload.get("ok"):
        raise ApiError(f"Slack token exchange rejected: {payload.get('error')}")

    user = payload.get("authed_user", {})
    if not user.get("access_token"):
        raise ApiError("Slack response had no user token — check the app's user scopes")

    tokens = {
        "access_token": user["access_token"],
        "refresh_token": user.get("refresh_token"),
        "expires_at": time.time() + int(user["expires_in"]) if user.get("expires_in") else 0,
        "scope": user.get("scope", ""),
        "user_id": user.get("id"),
        "team_id": (payload.get("team") or {}).get("id"),
    }
    secrets.set_slack_tokens(tokens)
    log.info("Slack connected for user %s", tokens.get("user_id"))
    return tokens
