"""Resolve app credentials: Settings-window values override baked-in defaults."""

from __future__ import annotations

from . import constants


def ms_tenant_id(settings) -> str:
    return (settings.ms_tenant_id or "").strip() or constants.MS_TENANT_ID


def ms_client_id(settings) -> str:
    return (settings.ms_client_id or "").strip() or constants.MS_CLIENT_ID


def ms_authority(settings) -> str:
    tenant = ms_tenant_id(settings) or "organizations"
    return f"https://login.microsoftonline.com/{tenant}"


def slack_client_id(settings) -> str:
    return (settings.slack_client_id or "").strip() or constants.SLACK_CLIENT_ID


def slack_client_secret(secrets) -> str:
    return secrets.get_slack_client_secret() or constants.SLACK_CLIENT_SECRET
