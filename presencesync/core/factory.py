"""Assemble a SyncEngine from settings + clients. Shared by the CLI and the app."""

from __future__ import annotations

from typing import Optional

from . import org_config
from .engine import SyncEngine
from .slack_client import SlackClient
from .store import SecretStore, Settings
from .sync import Reconciler
from .teams_client import TeamsClient


def build_engine(dry_run: bool = False, settings: Optional[Settings] = None) -> SyncEngine:
    settings = settings or Settings.load()
    org_config.seed_if_present(settings, SecretStore())
    teams = TeamsClient(settings)
    slack = SlackClient(settings=settings)
    reconciler = Reconciler(settings.to_sync_settings())
    return SyncEngine(settings, teams, slack, reconciler, dry_run=dry_run)
