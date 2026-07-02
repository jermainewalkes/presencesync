"""Windows system-tray app (pystray).

A worker thread runs the blocking sync cycle; pystray renders state on demand.
"""

from __future__ import annotations

import logging
import threading
import time

import pystray
from pystray import Menu, MenuItem

from ..core import constants, single_instance
from ..core.errors import PresenceSyncError
from ..core.factory import build_engine
from ..core.health import Health, HealthState, evaluate
from ..core.oauth_slack import connect_slack
from . import autostart, icons, settings

log = logging.getLogger(__name__)


def _ago(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


class PresenceSyncTray:
    def __init__(self) -> None:
        self.engine = build_engine()
        self._lock = threading.Lock()
        self._health = Health(HealthState.ERROR, "Starting")
        self._images = {state: icons.make_image(state) for state in HealthState}
        self.icon = pystray.Icon(constants.APP_NAME, self._images[HealthState.ERROR],
                                 constants.APP_NAME, menu=self._menu())
        self._stop = threading.Event()

    # Menu

    def _menu(self) -> Menu:
        return Menu(
            MenuItem(self._status_text, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(lambda item: "Microsoft: Connected" if self.engine.teams.is_connected() else "Connect Microsoft...",
                     self._on_microsoft),
            MenuItem(lambda item: "Slack: Connected" if self.engine.slack.is_connected() else "Connect Slack...",
                     self._on_slack),
            Menu.SEPARATOR,
            MenuItem("Sync Teams to Slack", self._toggle("teams_to_slack"),
                     checked=lambda item: self.engine.settings.teams_to_slack),
            MenuItem("Sync Slack to Teams", self._toggle("slack_to_teams"),
                     checked=lambda item: self.engine.settings.slack_to_teams),
            MenuItem("Pause Syncing", self._toggle("paused"),
                     checked=lambda item: self.engine.settings.paused),
            Menu.SEPARATOR,
            MenuItem("Settings...", lambda: settings.open_settings(self)),
            MenuItem("Statuses...", lambda: settings.open_statuses(self)),
            MenuItem("Setup Guide", lambda: settings.open_guide()),
            MenuItem("Open Logs...", lambda: settings.open_logs()),
            MenuItem("Start at Login", self._toggle_autostart,
                     checked=lambda item: autostart.is_enabled()),
            Menu.SEPARATOR,
            MenuItem(f"Quit {constants.APP_NAME}", self._quit),
        )

    def _status_text(self, item=None) -> str:
        with self._lock:
            health = self._health
        if self.engine.last_success:
            return f"{health.title} - {_ago(int(time.time() - self.engine.last_success))}"
        return health.title

    # Actions

    def _toggle(self, name):
        def handler(icon, item):
            self.set_direction(name, not getattr(self.engine.settings, name))
        return handler

    def set_direction(self, name: str, value: bool) -> None:
        setattr(self.engine.settings, name, value)
        if hasattr(self.engine.reconciler.settings, name):
            setattr(self.engine.reconciler.settings, name, value)
        self.engine.settings.save()

    def rebuild_teams_client(self) -> None:
        from ..core.teams_client import TeamsClient

        self.engine.teams = TeamsClient(self.engine.settings)

    def _on_microsoft(self, icon, item) -> None:
        if not self.engine.teams.is_connected():
            self.connect_microsoft()

    def _on_slack(self, icon, item) -> None:
        if not self.engine.slack.is_connected():
            self.connect_slack()

    def connect_microsoft(self) -> None:
        self._connect_in_background(self.engine.teams.connect, "Microsoft")

    def connect_slack(self) -> None:
        eng = self.engine
        self._connect_in_background(lambda: connect_slack(eng.slack.secrets, eng.settings), "Slack")

    def _connect_in_background(self, fn, label: str) -> None:
        def task():
            try:
                fn()
                self._notify(f"{label} connected")
            except PresenceSyncError as exc:
                self._notify(f"{label} sign-in failed: {exc}")
            except Exception:
                log.exception("connect %s failed", label)
                self._notify(f"{label} sign-in failed")

        threading.Thread(target=task, name=f"connect-{label}", daemon=True).start()

    def _toggle_autostart(self, icon, item) -> None:
        try:
            autostart.disable() if autostart.is_enabled() else autostart.enable()
        except Exception:
            log.exception("toggle autostart failed")

    def _notify(self, message: str) -> None:
        try:
            self.icon.notify(message, constants.APP_NAME)
        except Exception:
            log.info("notification: %s", message)

    def _quit(self, icon, item) -> None:
        self._stop.set()
        self.icon.stop()

    # Worker

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.engine.tick()
                health = evaluate(self.engine)
            except Exception:
                log.exception("sync tick failed")
                health = Health(HealthState.ERROR, "Sync error")
            with self._lock:
                old_state = self._health.state
                self._health = health
            if health.state != old_state:
                self.icon.icon = self._images[health.state]
            self.icon.title = f"{constants.APP_NAME}: {health.title}"
            self._stop.wait(max(self.engine.settings.poll_interval_seconds, 1))

    def run(self) -> int:
        threading.Thread(target=self._worker_loop, name="sync-worker", daemon=True).start()
        if not (self.engine.slack.is_connected() or self.engine.settings.slack_client_id):
            threading.Timer(1.0, lambda: settings.open_settings(self)).start()
        self.icon.run()
        return 0


def run_app() -> int:
    import os

    os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=constants.LOG_PATH,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not single_instance.acquire():
        log.info("PresenceSync is already running; this instance will exit")
        return 0
    return PresenceSyncTray().run()

