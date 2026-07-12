"""Shared exception types, so the health monitor can distinguish failure kinds."""


class PresenceSyncError(Exception):
    """Base class."""


class NeedsAuth(PresenceSyncError):
    """Credentials are missing or expired beyond silent recovery — user must reconnect."""


class ApiError(PresenceSyncError):
    """A Graph or Slack API call failed (network, 5xx, or an `ok: false` response)."""


class UpdateError(PresenceSyncError):
    """A self-update could not be applied; the user should update manually."""
