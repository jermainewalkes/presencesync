"""Unit tests for the reconciler — especially that the two sync directions
cannot feed each other. No network, auth, or GUI required.

Run:  python -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from presencesync.core.models import SlackProfile, SlackStatus, TeamsPresence  # noqa: E402
from presencesync.core.sync import Reconciler, SyncSettings, TeamsAction  # noqa: E402


def step(rec, teams, slack):
    """Plan one cycle and commit it, as the app does on success."""
    plan = rec.plan(teams, slack)
    rec.commit(plan)
    return plan


AVAILABLE = TeamsPresence("Available", "Available")
IN_A_CALL = TeamsPresence("Busy", "InACall")
IN_A_MEETING = TeamsPresence("Busy", "InAMeeting")
INJECTED_BUSY = TeamsPresence("Busy", "Busy")  # what our huddle injection looks like

NO_HUDDLE = SlackProfile(in_huddle=False)
HUDDLE = SlackProfile(in_huddle=True)


class TeamsToSlackTests(unittest.TestCase):
    def test_call_sets_slack_status(self):
        rec = Reconciler()
        plan = step(rec, IN_A_CALL, NO_HUDDLE)
        self.assertEqual(plan.slack_status, SlackStatus("On a Teams call", ":headphones:"))
        self.assertIs(plan.teams_action, TeamsAction.NONE)

    def test_echo_suppressed_next_cycle(self):
        rec = Reconciler()
        step(rec, IN_A_CALL, NO_HUDDLE)  # sets it
        # Next cycle Slack now reports our text back to us → must be a no-op.
        slack_now = SlackProfile(in_huddle=False, status_text="On a Teams call", status_emoji=":headphones:")
        plan = step(rec, IN_A_CALL, slack_now)
        self.assertIsNone(plan.slack_status)

    def test_returning_available_clears_slack(self):
        rec = Reconciler()
        step(rec, IN_A_CALL, NO_HUDDLE)
        slack_now = SlackProfile(in_huddle=False, status_text="On a Teams call")
        plan = step(rec, AVAILABLE, slack_now)
        self.assertIsNotNone(plan.slack_status)
        self.assertTrue(plan.slack_status.is_clear)

    def test_reasserts_after_external_clear(self):
        rec = Reconciler()
        step(rec, IN_A_CALL, NO_HUDDLE)  # sets "On a Teams call"
        echoed = SlackProfile(in_huddle=False, status_text="On a Teams call", status_emoji=":headphones:")
        self.assertIsNone(step(rec, IN_A_CALL, echoed).slack_status)  # reflected → no-op
        # Cleared externally while still in the call → we must restore it.
        cleared = SlackProfile(in_huddle=False, status_text="", status_emoji="")
        plan = step(rec, IN_A_CALL, cleared)
        self.assertEqual(plan.slack_status, SlackStatus("On a Teams call", ":headphones:"))

    def test_manual_slack_status_not_clobbered(self):
        rec = Reconciler()
        manual = SlackProfile(in_huddle=False, status_text="Lunch", status_emoji=":sandwich:")
        plan = step(rec, IN_A_MEETING, manual)
        self.assertIsNone(plan.slack_status)

    def test_already_clear_is_noop(self):
        rec = Reconciler()
        plan = step(rec, AVAILABLE, NO_HUDDLE)
        self.assertIsNone(plan.slack_status)
        self.assertTrue(plan.is_noop)

    def test_direction_disabled(self):
        rec = Reconciler(SyncSettings(teams_to_slack=False))
        plan = step(rec, IN_A_CALL, NO_HUDDLE)
        self.assertIsNone(plan.slack_status)


class SlackToTeamsTests(unittest.TestCase):
    def test_huddle_sets_teams_busy(self):
        rec = Reconciler()
        plan = step(rec, AVAILABLE, HUDDLE)
        self.assertIs(plan.teams_action, TeamsAction.SET_BUSY)
        self.assertTrue(rec.teams_injected)

    def test_huddle_end_clears_teams(self):
        rec = Reconciler()
        step(rec, AVAILABLE, HUDDLE)            # inject
        plan = step(rec, INJECTED_BUSY, NO_HUDDLE)  # huddle gone
        self.assertIs(plan.teams_action, TeamsAction.CLEAR)
        self.assertFalse(rec.teams_injected)

    def test_real_call_beats_huddle(self):
        # In a real Teams call AND a Slack huddle: do not inject; mirror the real call.
        rec = Reconciler()
        plan = step(rec, IN_A_CALL, HUDDLE)
        self.assertIs(plan.teams_action, TeamsAction.NONE)
        self.assertEqual(plan.slack_status, SlackStatus("On a Teams call", ":headphones:"))

    def test_real_call_clears_existing_injection(self):
        rec = Reconciler()
        step(rec, AVAILABLE, HUDDLE)  # inject
        plan = step(rec, IN_A_CALL, HUDDLE)  # a real call appears
        self.assertIs(plan.teams_action, TeamsAction.CLEAR)

    def test_direction_disabled_clears_prior_injection(self):
        rec = Reconciler()
        step(rec, AVAILABLE, HUDDLE)  # inject while enabled
        rec.settings.slack_to_teams = False
        plan = step(rec, INJECTED_BUSY, HUDDLE)
        self.assertIs(plan.teams_action, TeamsAction.CLEAR)


class LoopPreventionTests(unittest.TestCase):
    def test_injected_busy_never_bounces_to_slack(self):
        """The crux: a Slack huddle injects Teams Busy, and that Busy must NOT come
        back around to set a Slack status."""
        rec = Reconciler()

        # Cycle 1 — huddle starts, Teams still shows real "Available".
        p1 = step(rec, AVAILABLE, HUDDLE)
        self.assertIs(p1.teams_action, TeamsAction.SET_BUSY)
        self.assertIsNone(p1.slack_status)  # Slack text untouched by the huddle

        # Cycle 2 — Teams now reports our injected Busy. Teams→Slack must stay silent.
        p2 = step(rec, INJECTED_BUSY, HUDDLE)
        self.assertIs(p2.teams_action, TeamsAction.NONE)
        self.assertIsNone(p2.slack_status)

        # Cycle 3 — huddle ends; we clear Teams, still no Slack write.
        p3 = step(rec, INJECTED_BUSY, NO_HUDDLE)
        self.assertIs(p3.teams_action, TeamsAction.CLEAR)
        self.assertIsNone(p3.slack_status)

        # Cycle 4 — Teams back to real Available; everything settled.
        p4 = step(rec, AVAILABLE, NO_HUDDLE)
        self.assertTrue(p4.is_noop)

    def test_huddle_does_not_change_slack_text(self):
        rec = Reconciler()
        # Even across several huddle cycles, Slack status text is never set by us.
        for teams in (AVAILABLE, INJECTED_BUSY, INJECTED_BUSY):
            plan = step(rec, teams, HUDDLE)
            self.assertIsNone(plan.slack_status)


class EdgeCaseTests(unittest.TestCase):
    def test_teams_unreadable_but_huddle_still_injects(self):
        rec = Reconciler()
        self.assertIs(step(rec, None, HUDDLE).teams_action, TeamsAction.SET_BUSY)

    def test_slack_unreadable_still_mirrors_teams_call(self):
        rec = Reconciler()
        plan = step(rec, IN_A_CALL, None)
        self.assertEqual(plan.slack_status, SlackStatus("On a Teams call", ":headphones:"))

    def test_both_directions_disabled_is_noop(self):
        rec = Reconciler(SyncSettings(teams_to_slack=False, slack_to_teams=False))
        self.assertTrue(step(rec, IN_A_CALL, HUDDLE).is_noop)

    def test_unknown_activity_clears_slack(self):
        rec = Reconciler()
        step(rec, IN_A_CALL, NO_HUDDLE)
        slack_now = SlackProfile(in_huddle=False, status_text="On a Teams call")
        plan = step(rec, TeamsPresence("Away", "Away"), slack_now)
        self.assertIsNotNone(plan.slack_status)
        self.assertTrue(plan.slack_status.is_clear)


if __name__ == "__main__":
    unittest.main(verbosity=2)
