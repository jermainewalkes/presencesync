"""SyncEngine runs one reconcile cycle per tick and tracks health-relevant state."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import constants
from .errors import NeedsAuth, PresenceSyncError
from .models import SlackProfile, TeamsPresence
from .slack_client import SlackClient
from .store import Settings
from .sync import Reconciler, SyncPlan, TeamsAction
from .teams_client import TeamsClient

log = logging.getLogger(__name__)


@dataclass
class CycleResult:
    teams: Optional[TeamsPresence]
    slack: Optional[SlackProfile]
    plan: Optional[SyncPlan]
    applied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    paused: bool = False


class SyncEngine:
    def __init__(
        self,
        settings: Settings,
        teams: TeamsClient,
        slack: SlackClient,
        reconciler: Reconciler,
        dry_run: bool = False,
    ) -> None:
        self.settings = settings
        self.teams = teams
        self.slack = slack
        self.reconciler = reconciler
        self.dry_run = dry_run
        # Health-relevant timestamps/flags.
        self.last_success: float = 0.0
        self.last_change: float = 0.0
        self.last_error: Optional[str] = None
        self.needs_auth: set[str] = set()  # {"teams", "slack"}

    def tick(self) -> CycleResult:
        if self.settings.paused:
            return CycleResult(None, None, None, paused=True)

        errors: list[str] = []
        teams_presence: Optional[TeamsPresence] = None
        slack_profile: Optional[SlackProfile] = None

        if self.teams.is_connected():
            try:
                teams_presence = self.teams.get_presence()
                self.needs_auth.discard("teams")
            except NeedsAuth as exc:
                self.needs_auth.add("teams")
                errors.append(f"Teams: {exc}")
            except PresenceSyncError as exc:
                errors.append(f"Teams: {exc}")

        if self.slack.is_connected():
            try:
                slack_profile = self.slack.get_profile()
                self.needs_auth.discard("slack")
            except NeedsAuth as exc:
                self.needs_auth.add("slack")
                errors.append(f"Slack: {exc}")
            except PresenceSyncError as exc:
                errors.append(f"Slack: {exc}")

        plan = self.reconciler.plan(teams_presence, slack_profile)

        applied: list[str] = []
        if self.dry_run:
            applied = self._describe(plan)
        elif not errors or not plan.is_noop:
            try:
                applied = self._apply(plan)
                self.reconciler.commit(plan)
                if applied:
                    self.last_change = time.time()
            except NeedsAuth as exc:
                self.needs_auth.add("slack" if "Slack" in str(exc) else "teams")
                errors.append(f"apply: {exc}")
            except PresenceSyncError as exc:
                errors.append(f"apply: {exc}")

        self.last_error = errors[-1] if errors else None
        if not errors:
            self.last_success = time.time()
        if applied:
            for line in applied:
                log.info("%s%s", "[dry-run] " if self.dry_run else "", line)
        return CycleResult(teams_presence, slack_profile, plan, applied, errors)

    # Apply / describe
    def _apply(self, plan: SyncPlan) -> list[str]:
        done: list[str] = []
        if plan.slack_status is not None:
            self.slack.set_status(plan.slack_status)
            done.append(plan.slack_reason)
        if plan.teams_action is TeamsAction.SET_BUSY:
            self.teams.set_preferred_presence()
            self.teams.set_status_message(self.settings.huddle_message or constants.HUDDLE_TEAMS_MESSAGE)
            done.append(plan.teams_reason)
        elif plan.teams_action is TeamsAction.CLEAR:
            self.teams.clear_preferred_presence()
            self.teams.clear_status_message()
            done.append(plan.teams_reason)
        return done

    @staticmethod
    def _describe(plan: SyncPlan) -> list[str]:
        lines: list[str] = []
        if plan.slack_status is not None:
            lines.append(f"would update Slack — {plan.slack_reason}")
        if plan.teams_action is not TeamsAction.NONE:
            lines.append(f"would update Teams — {plan.teams_reason}")
        return lines
