"""SyncEngine tests — that a cycle applies the right writes, honours dry-run and
pause, and turns read failures into health state instead of crashing.

Run:  python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presencesync.core.engine import SyncEngine  # noqa: E402
from presencesync.core.errors import NeedsAuth  # noqa: E402
from presencesync.core.models import SlackProfile, TeamsPresence  # noqa: E402
from presencesync.core.store import Settings  # noqa: E402
from presencesync.core.sync import Reconciler  # noqa: E402


class FakeTeams:
    def __init__(self, presence=None, connected=True, error=None):
        self.presence = presence
        self.connected = connected
        self.error = error
        self.calls = []

    def is_connected(self):
        return self.connected

    def get_presence(self):
        if self.error:
            raise self.error
        return self.presence

    def set_preferred_presence(self, *a, **k):
        self.calls.append("set_busy")

    def clear_preferred_presence(self):
        self.calls.append("clear_presence")

    def set_status_message(self, text):
        self.calls.append(("msg", text))

    def clear_status_message(self):
        self.calls.append("clear_msg")


class FakeSlack:
    def __init__(self, profile=None, connected=True, error=None):
        self.profile = profile
        self.connected = connected
        self.error = error
        self.status_calls = []

    def is_connected(self):
        return self.connected

    def get_profile(self):
        if self.error:
            raise self.error
        return self.profile

    def set_status(self, status):
        self.status_calls.append(status)


def make_engine(teams, slack, dry_run=False, **settings_kw):
    settings = Settings(**settings_kw)
    return SyncEngine(settings, teams, slack, Reconciler(settings.to_sync_settings()), dry_run=dry_run)


class EngineTests(unittest.TestCase):
    def test_teams_call_writes_slack_status(self):
        teams = FakeTeams(TeamsPresence("Busy", "InACall"))
        slack = FakeSlack(SlackProfile(in_huddle=False))
        result = make_engine(teams, slack).tick()
        self.assertEqual(len(slack.status_calls), 1)
        self.assertEqual(slack.status_calls[0].text, "On a Teams call")
        self.assertTrue(result.applied)

    def test_huddle_sets_teams_busy(self):
        teams = FakeTeams(TeamsPresence("Available", "Available"))
        slack = FakeSlack(SlackProfile(in_huddle=True))
        make_engine(teams, slack).tick()
        self.assertIn("set_busy", teams.calls)
        self.assertIn(("msg", "In a Slack huddle"), teams.calls)

    def test_dry_run_writes_nothing(self):
        teams = FakeTeams(TeamsPresence("Busy", "InACall"))
        slack = FakeSlack(SlackProfile(in_huddle=False))
        result = make_engine(teams, slack, dry_run=True).tick()
        self.assertEqual(slack.status_calls, [])
        self.assertEqual(teams.calls, [])
        self.assertTrue(result.applied)  # described, not executed

    def test_paused_is_noop(self):
        teams = FakeTeams(TeamsPresence("Busy", "InACall"))
        slack = FakeSlack(SlackProfile(in_huddle=True))
        result = make_engine(teams, slack, paused=True).tick()
        self.assertTrue(result.paused)
        self.assertEqual(slack.status_calls, [])
        self.assertEqual(teams.calls, [])

    def test_read_error_becomes_needs_auth_not_crash(self):
        teams = FakeTeams(error=NeedsAuth("expired"))
        slack = FakeSlack(SlackProfile(in_huddle=False))
        engine = make_engine(teams, slack)
        result = engine.tick()  # must not raise
        self.assertIn("teams", engine.needs_auth)
        self.assertTrue(result.errors)

    def test_disconnected_services_are_skipped(self):
        teams = FakeTeams(connected=False)
        slack = FakeSlack(connected=False)
        result = make_engine(teams, slack).tick()
        self.assertEqual(slack.status_calls, [])
        self.assertEqual(teams.calls, [])
        self.assertFalse(result.errors)

    def test_custom_status_text_is_used(self):
        teams = FakeTeams(TeamsPresence("Busy", "InACall"))
        slack = FakeSlack(SlackProfile(in_huddle=False))
        engine = make_engine(teams, slack, status_map={"call": {"text": "On a video call", "emoji": ":phone:"}})
        engine.tick()
        self.assertEqual(slack.status_calls[0].text, "On a video call")
        self.assertEqual(slack.status_calls[0].emoji, ":phone:")

    def test_custom_huddle_message_is_used(self):
        teams = FakeTeams(TeamsPresence("Available", "Available"))
        slack = FakeSlack(SlackProfile(in_huddle=True))
        make_engine(teams, slack, huddle_message="Heads down").tick()
        self.assertIn(("msg", "Heads down"), teams.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
