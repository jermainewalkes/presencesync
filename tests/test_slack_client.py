"""Slack client tests — token auto-refresh, huddle parsing, and error mapping,
all with mocked HTTP so no live Slack (or Keychain) is touched.

Run:  python -m unittest discover -s tests
"""

import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presencesync.core.errors import ApiError, NeedsAuth  # noqa: E402
from presencesync.core.models import SlackStatus  # noqa: E402
from presencesync.core.slack_client import SlackClient  # noqa: E402
from presencesync.core.store import Settings  # noqa: E402

POST = "requests.Session.post"
REQUEST = "requests.Session.request"


class FakeSecrets:
    def __init__(self, tokens=None, client_secret="csecret"):
        self._tokens = tokens
        self._client_secret = client_secret

    def get_slack_tokens(self):
        return dict(self._tokens) if self._tokens else None

    def set_slack_tokens(self, tokens):
        self._tokens = dict(tokens)

    def get_slack_client_secret(self):
        return self._client_secret

    def clear_slack_tokens(self):
        self._tokens = None


def make_client(tokens=None, client_secret="csecret", client_id="cid"):
    return SlackClient(
        secrets=FakeSecrets(tokens, client_secret),
        settings=Settings(slack_client_id=client_id),
    )


def resp(payload):
    m = mock.Mock()
    m.json.return_value = payload
    m.ok = payload.get("ok", True)
    m.status_code = 200
    m.text = str(payload)
    return m


class TokenRefreshTests(unittest.TestCase):
    def _near_expiry(self):
        return {"access_token": "old", "refresh_token": "r1", "expires_at": time.time() + 100}

    def test_refreshes_when_near_expiry_and_persists(self):
        c = make_client(self._near_expiry())
        payload = {"ok": True, "access_token": "new", "refresh_token": "r2", "expires_in": 43200}
        with mock.patch(POST, return_value=resp(payload)) as post:
            token = c._access_token()
        self.assertEqual(token, "new")
        post.assert_called_once()
        saved = c.secrets.get_slack_tokens()
        self.assertEqual(saved["access_token"], "new")
        self.assertEqual(saved["refresh_token"], "r2")
        self.assertGreater(saved["expires_at"], time.time() + 43000)

    def test_reads_tokens_from_authed_user_nesting(self):
        c = make_client(self._near_expiry())
        payload = {"ok": True, "authed_user": {"access_token": "newu", "refresh_token": "r2u", "expires_in": 43200}}
        with mock.patch(POST, return_value=resp(payload)):
            self.assertEqual(c._access_token(), "newu")

    def test_no_refresh_when_token_is_fresh(self):
        c = make_client({"access_token": "tok", "refresh_token": "r1", "expires_at": time.time() + 99999})
        with mock.patch(POST) as post:
            self.assertEqual(c._access_token(), "tok")
        post.assert_not_called()

    def test_no_refresh_for_non_rotating_token(self):
        c = make_client({"access_token": "tok", "expires_at": 0})  # no refresh_token
        with mock.patch(POST) as post:
            self.assertEqual(c._access_token(), "tok")
        post.assert_not_called()

    def test_refresh_rejected_raises_needs_auth(self):
        c = make_client(self._near_expiry())
        with mock.patch(POST, return_value=resp({"ok": False, "error": "invalid_refresh_token"})):
            with self.assertRaises(NeedsAuth):
                c._access_token()

    def test_refresh_without_client_creds_raises(self):
        c = make_client(self._near_expiry(), client_secret="", client_id="")
        with self.assertRaises(NeedsAuth):
            c._access_token()

    def test_refresh_missing_access_token_raises(self):
        c = make_client(self._near_expiry())
        with mock.patch(POST, return_value=resp({"ok": True, "refresh_token": "r2"})):
            with self.assertRaises(ApiError):
                c._access_token()

    def test_refresh_without_expires_in_still_advances(self):
        c = make_client(self._near_expiry())
        with mock.patch(POST, return_value=resp({"ok": True, "access_token": "new"})):
            c._access_token()
        # expiry pushed well into the future so we don't refresh-storm
        self.assertGreater(c.secrets.get_slack_tokens()["expires_at"], time.time() + 3600)

    def test_not_connected_raises(self):
        with self.assertRaises(NeedsAuth):
            make_client(None)._access_token()

    def test_has_refresh_token(self):
        self.assertTrue(make_client({"access_token": "t", "refresh_token": "r"}).has_refresh_token())
        self.assertFalse(make_client({"access_token": "t"}).has_refresh_token())
        self.assertFalse(make_client(None).has_refresh_token())


class ApiTests(unittest.TestCase):
    def _static(self):
        return make_client({"access_token": "tok", "expires_at": 0})

    def test_get_profile_detects_huddle(self):
        payload = {"ok": True, "profile": {"huddle_state": "in_a_huddle", "status_text": "Busy", "status_emoji": ":x:"}}
        with mock.patch(REQUEST, return_value=resp(payload)):
            prof = self._static().get_profile()
        self.assertTrue(prof.in_huddle)
        self.assertEqual(prof.status_text, "Busy")

    def test_get_profile_no_huddle(self):
        payload = {"ok": True, "profile": {"huddle_state": "default", "status_text": ""}}
        with mock.patch(REQUEST, return_value=resp(payload)):
            self.assertFalse(self._static().get_profile().in_huddle)

    def test_auth_error_maps_to_needs_auth(self):
        with mock.patch(REQUEST, return_value=resp({"ok": False, "error": "token_expired"})):
            with self.assertRaises(NeedsAuth):
                self._static().get_profile()

    def test_other_error_maps_to_api_error(self):
        with mock.patch(REQUEST, return_value=resp({"ok": False, "error": "ratelimited"})):
            with self.assertRaises(ApiError):
                self._static().get_profile()

    def test_rate_limited_maps_to_api_error(self):
        m = mock.Mock()
        m.status_code = 429
        m.headers = {"Retry-After": "30"}
        with mock.patch(REQUEST, return_value=m):
            with self.assertRaises(ApiError):
                self._static().get_profile()

    def test_set_status_posts_ok(self):
        with mock.patch(REQUEST, return_value=resp({"ok": True})) as req:
            self._static().set_status(SlackStatus("On a Teams call", ":headphones:"))
        req.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
