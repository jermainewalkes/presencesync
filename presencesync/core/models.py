"""Dependency-free data types shared across the engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamsPresence:
    """A snapshot of Microsoft Teams presence from GET /me/presence."""

    availability: str  # Available, Busy, Away, BeRightBack, DoNotDisturb, Offline, ...
    activity: str      # Available, InACall, InAMeeting, Presenting, OnThePhone, Busy, ...


@dataclass(frozen=True)
class SlackProfile:
    """The bits of a Slack user profile we care about (from users.profile.get)."""

    in_huddle: bool
    status_text: str = ""
    status_emoji: str = ""


@dataclass(frozen=True)
class SlackStatus:
    """A Slack custom status we want to set (users.profile.set)."""

    text: str
    emoji: str
    expiration: int = 0  # epoch seconds; 0 = no expiration

    @property
    def is_clear(self) -> bool:
        return not self.text and not self.emoji

    @classmethod
    def cleared(cls) -> "SlackStatus":
        return cls("", "", 0)
