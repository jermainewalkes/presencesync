"""One reusable connection test, surfaced both in the Settings window ("Test
connection") and the CLI (`--test`). It verifies each token and reports the live
state — which also confirms Slack's huddle detection against a real response.
"""

from __future__ import annotations

from .errors import NeedsAuth, PresenceSyncError


def test_connections(engine) -> str:
    lines = []

    # Microsoft
    if not engine.teams.is_connected():
        lines.append("Microsoft — not connected")
    else:
        try:
            p = engine.teams.get_presence()
            lines.append(f"Microsoft — OK · {p.activity} ({p.availability})")
        except NeedsAuth as exc:
            lines.append(f"Microsoft — reconnect needed: {exc}")
        except PresenceSyncError as exc:
            lines.append(f"Microsoft — error: {exc}")

    # Slack
    if not engine.slack.is_connected():
        lines.append("Slack — not connected")
    else:
        try:
            engine.slack.validate_token()
            prof = engine.slack.get_profile()
            bits = ["in a huddle" if prof.in_huddle else "no huddle"]
            if prof.status_text:
                bits.append(f"status “{prof.status_text}”")
            lines.append("Slack — OK · " + ", ".join(bits))
        except NeedsAuth as exc:
            lines.append(f"Slack — reconnect needed: {exc}")
        except PresenceSyncError as exc:
            lines.append(f"Slack — error: {exc}")

    return "\n".join(lines)
