"""Static configuration: app identity, API endpoints, scopes, and default mappings."""

from __future__ import annotations

import os
import sys
from collections import namedtuple
# App identity / paths
APP_NAME = "PresenceSync"
BUNDLE_ID = "com.jermainewalkes.presencesync"

if sys.platform == "win32":
    APP_SUPPORT_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
else:
    APP_SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
SETTINGS_PATH = os.path.join(APP_SUPPORT_DIR, "settings.json")
LOG_PATH = os.path.join(APP_SUPPORT_DIR, "presencesync.log")


def resource_path(name: str) -> str:
    """Locate a bundled resource, whether running from source or a py2app .app."""
    if getattr(sys, "frozen", False):
        base = os.path.join(os.path.dirname(sys.executable), os.pardir, "Resources")
    else:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources")
    return os.path.abspath(os.path.join(base, name))


SETUP_GUIDE_PATH = resource_path("setup_guide.html")

POLL_INTERVAL_SECONDS = 15
# Microsoft Graph / MSAL. Tenant and client ids are supplied by the user in the
# Settings window (or an org-config.json seed); see credentials.py.
MS_TENANT_ID = ""
MS_CLIENT_ID = ""
# Presence.ReadWrite covers both reading our presence and setting preferred presence.
MS_SCOPES = ["Presence.Read", "Presence.ReadWrite"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Slack OAuth / Web API
# Slack app credentials (https://api.slack.com/apps). Entered in the app's Settings
# window and stored in the Keychain (secret) + settings.json (client id). These env
# vars are an optional convenience for headless/CLI use only.
SLACK_CLIENT_ID = os.environ.get("PRESENCESYNC_SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = os.environ.get("PRESENCESYNC_SLACK_CLIENT_SECRET", "")
SLACK_USER_SCOPES = ["users.profile:read", "users.profile:write", "users:read"]
SLACK_API = "https://slack.com/api"
SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
# Loopback redirect for the OAuth code. Must be added verbatim to the Slack app's
# "Redirect URLs". A fixed port keeps that registration simple.
SLACK_REDIRECT_PORT = 53682
SLACK_REDIRECT_URI = f"http://localhost:{SLACK_REDIRECT_PORT}/callback"
# Sync mapping defaults
# Teams activities that represent a genuine call/meeting. These drive Teams→Slack
# AND mark "the user is really busy in Teams" so a Slack huddle won't override them.
REAL_CALL_ACTIVITIES = frozenset(
    {"InACall", "OnThePhone", "InAConferenceCall", "InAMeeting", "Presenting"}
)

# User-facing status categories: each groups one or more Teams activities and carries
# the default Slack text/emoji. Users override these in the Statuses window.
StatusCategory = namedtuple("StatusCategory", "key label activities text emoji")
STATUS_CATEGORIES = (
    StatusCategory("call", "On a call", ("InACall", "OnThePhone", "InAConferenceCall"), "On a Teams call", ":headphones:"),
    StatusCategory("meeting", "In a meeting", ("InAMeeting",), "In a Teams meeting", ":spiral_calendar_pad:"),
    StatusCategory("presenting", "Presenting", ("Presenting",), "Presenting", ":projector:"),
    StatusCategory("busy", "Busy", ("Busy",), "Busy", ":no_entry:"),
)

# Teams activity → Slack custom status, expanded from the categories above.
# NOTE: plain "Busy" is mapped too, but the reconciler only applies it when the Busy
# was NOT self-injected by us (a Slack huddle), which prevents a feedback loop.
DEFAULT_TEAMS_TO_SLACK = {
    activity: {"text": c.text, "emoji": c.emoji}
    for c in STATUS_CATEGORIES
    for activity in c.activities
}

# Slack huddle → Teams preferred presence + status message.
HUDDLE_TEAMS_AVAILABILITY = "Busy"
HUDDLE_TEAMS_ACTIVITY = "Busy"
HUDDLE_TEAMS_MESSAGE = "In a Slack huddle"
# Preferred presence is sticky; we re-assert it with a rolling expiry while the huddle
# lasts and clear it explicitly when the huddle ends.
HUDDLE_PRESENCE_EXPIRATION = "PT1H"
