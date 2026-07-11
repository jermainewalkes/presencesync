"""Map engine state to a tri-state health signal for the tray icon.

OK: connected and syncing. WARNING: degraded or partially configured.
ERROR: user action required (reconnect or configure).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

# Treat a connected token within this window of expiry (with no refresh capability)
# as "expiring soon".
_EXPIRY_WARN_SECONDS = 24 * 3600


class HealthState(Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Health:
    state: HealthState
    title: str
    detail: list[str] = field(default_factory=list)


def evaluate(engine) -> Health:
    teams_conn = engine.teams.is_connected()
    slack_conn = engine.slack.is_connected()

    if not teams_conn and not slack_conn:
        return Health(HealthState.ERROR, "Not Connected", ["Sign in to Microsoft and Slack"])

    if engine.needs_auth:
        names = ", ".join(sorted(s.capitalize() for s in engine.needs_auth))
        return Health(
            HealthState.ERROR,
            f"{names}: Reconnect Needed",
            [engine.last_error or "Authentication expired"],
        )

    if engine.settings.paused:
        return Health(HealthState.WARNING, "Paused", ["Syncing is paused"])

    if not (teams_conn and slack_conn):
        missing = "Slack" if not slack_conn else "Microsoft"
        return Health(
            HealthState.WARNING,
            f"{missing} Not Connected",
            [f"Connect {missing} for two-way sync"],
        )

    # Both connected: look for degraded conditions.
    detail: list[str] = []
    now = time.time()
    interval = max(engine.settings.poll_interval_seconds, 1)

    for name, client in (("Microsoft", engine.teams), ("Slack", engine.slack)):
        exp = getattr(client, "token_expires_at", 0) or 0
        has_refresh = name == "Microsoft" or engine.slack.has_refresh_token()
        if exp and not has_refresh and exp - now < _EXPIRY_WARN_SECONDS:
            detail.append(f"{name} sign-in expires soon")

    if engine.last_error and (engine.last_success == 0 or now - engine.last_success > 3 * interval):
        return Health(HealthState.WARNING, "Sync Issue", [engine.last_error])

    if detail:
        return Health(HealthState.WARNING, "Sign-In Expiring", detail)

    return Health(HealthState.OK, "Synced", [])
