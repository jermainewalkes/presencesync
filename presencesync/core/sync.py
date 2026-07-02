"""The reconciler: pure planning of Slack/Teams writes for each cycle.

Loop prevention: Teams-to-Slack is suppressed while our own huddle injection is
masking the real Teams presence, and Slack-to-Teams reacts only to huddle_state,
never to status text. Manual Slack statuses are never overwritten, only our own
injected Teams presence is cleared, and a real Teams call outranks a huddle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

from . import constants
from .models import SlackProfile, SlackStatus, TeamsPresence


class TeamsAction(Enum):
    NONE = auto()
    SET_BUSY = auto()  # set preferred presence Busy + "In a Slack huddle" message
    CLEAR = auto()     # clear preferred presence + status message


@dataclass
class SyncSettings:
    teams_to_slack: bool = True
    slack_to_teams: bool = True
    # activity -> {"text", "emoji"}
    teams_to_slack_map: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.teams_to_slack_map is None:
            self.teams_to_slack_map = dict(constants.DEFAULT_TEAMS_TO_SLACK)


@dataclass
class SyncPlan:
    slack_status: Optional[SlackStatus]  # None = leave Slack alone
    slack_reason: str
    teams_action: TeamsAction
    teams_reason: str

    @property
    def is_noop(self) -> bool:
        return self.slack_status is None and self.teams_action is TeamsAction.NONE


class Reconciler:
    def __init__(self, settings: Optional[SyncSettings] = None) -> None:
        self.settings = settings or SyncSettings()
        self._last_pushed_slack: Optional[SlackStatus] = None
        self._teams_injected: bool = False

    # State introspection (used by the health monitor / tests)
    @property
    def teams_injected(self) -> bool:
        return self._teams_injected

    def _managed_texts(self) -> set[str]:
        texts = {m["text"] for m in self.settings.teams_to_slack_map.values() if m.get("text")}
        texts.add(constants.HUDDLE_TEAMS_MESSAGE)
        return texts

    def _desired_slack_status(self, teams: TeamsPresence) -> SlackStatus:
        entry = self.settings.teams_to_slack_map.get(teams.activity)
        if entry is None and teams.availability == "Busy":
            entry = self.settings.teams_to_slack_map.get("Busy")
        if entry and (entry.get("text") or entry.get("emoji")):
            return SlackStatus(entry.get("text", ""), entry.get("emoji", ""))
        return SlackStatus.cleared()

    def _slack_is_ours_or_empty(self, slack: Optional[SlackProfile]) -> bool:
        if slack is None or not slack.status_text:
            return True
        if slack.status_text in self._managed_texts():
            return True
        if self._last_pushed_slack and slack.status_text == self._last_pushed_slack.text:
            return True
        return False

    def plan(
        self, teams: Optional[TeamsPresence], slack: Optional[SlackProfile]
    ) -> SyncPlan:
        slack_status: Optional[SlackStatus] = None
        slack_reason = "no change"
        teams_action = TeamsAction.NONE
        teams_reason = "no change"

        # Slack → Teams
        in_real_call = teams is not None and teams.activity in constants.REAL_CALL_ACTIVITIES
        if self.settings.slack_to_teams and slack is not None:
            want_busy = slack.in_huddle and not in_real_call
        else:
            want_busy = False

        if want_busy and not self._teams_injected:
            teams_action = TeamsAction.SET_BUSY
            teams_reason = "Slack huddle → set Teams Busy"
        elif not want_busy and self._teams_injected:
            teams_action = TeamsAction.CLEAR
            if slack is not None and not slack.in_huddle:
                teams_reason = "Slack huddle ended → clear Teams presence"
            elif in_real_call:
                teams_reason = "real Teams call takes over → clear injected presence"
            else:
                teams_reason = "Slack→Teams disabled → clear injected presence"

        # Teams → Slack
        # Suppressed while our own injection is masking the real Teams presence.
        if self._teams_injected:
            slack_reason = "suppressed (Teams presence is self-injected)"
        elif self.settings.teams_to_slack and teams is not None:
            desired = self._desired_slack_status(teams)
            if not self._slack_is_ours_or_empty(slack):
                slack_reason = "manual Slack status present; leaving it alone"
            elif desired == self._last_pushed_slack:
                slack_reason = "already up to date"
            elif desired.is_clear and (slack is None or not slack.status_text):
                slack_reason = "already clear"
            else:
                slack_status = desired
                slack_reason = (
                    f"Teams {teams.activity} → clear Slack status"
                    if desired.is_clear
                    else f"Teams {teams.activity} → Slack {desired.text!r}"
                )

        return SyncPlan(slack_status, slack_reason, teams_action, teams_reason)

    def commit(self, plan: SyncPlan) -> None:
        """Advance internal state after a plan has been applied successfully."""
        if plan.slack_status is not None:
            self._last_pushed_slack = plan.slack_status
        if plan.teams_action is TeamsAction.SET_BUSY:
            self._teams_injected = True
        elif plan.teams_action is TeamsAction.CLEAR:
            self._teams_injected = False
