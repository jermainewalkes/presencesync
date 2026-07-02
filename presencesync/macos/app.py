"""macOS menu-bar app (rumps).

A worker thread runs the blocking sync cycle; a main-thread timer renders state.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time

import rumps
from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

from . import login_item
from ..core import constants, credentials
from ..core.errors import PresenceSyncError
from ..core.factory import build_engine
from ..core.health import Health, HealthState, evaluate
from ..core.oauth_slack import connect_slack
from ..core import single_instance

log = logging.getLogger(__name__)

# Text fallback used only if image rendering is unavailable.
_FALLBACK_GLYPH = {
    HealthState.OK: "🟢",
    HealthState.WARNING: "🟡",
    HealthState.ERROR: "🔴",
}


def _ago(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


class PresenceSyncApp(rumps.App):
    def __init__(self) -> None:
        super().__init__(constants.APP_NAME, title="", quit_button=None)
        self.engine = build_engine()
        self._lock = threading.Lock()
        self._health: Health = Health(HealthState.ERROR, "Starting…")
        self._snapshot: dict = {"ms": False, "slack": False, "last_success": 0.0}
        self._icons = self._render_icons()
        self._icon_key = None
        self._settings_controller = None
        self._statuses_controller = None
        self._onboarded = False

        self._build_menu()
        self._apply_icon(HealthState.ERROR)

        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, name="sync-worker", daemon=True)
        self._worker.start()

        self._ui_timer = rumps.Timer(self._refresh_ui, 2)
        self._ui_timer.start()

    # Menu construction
    def _build_menu(self) -> None:
        self.status_item = rumps.MenuItem("Starting…")
        self.ms_item = rumps.MenuItem("Microsoft: …", callback=self._on_ms_click)
        self.slack_item = rumps.MenuItem("Slack: …", callback=self._on_slack_click)
        self.t2s_item = rumps.MenuItem("Sync Teams → Slack", callback=self._toggle_t2s)
        self.s2t_item = rumps.MenuItem("Sync Slack → Teams", callback=self._toggle_s2t)
        self.pause_item = rumps.MenuItem("Pause Syncing", callback=self._toggle_pause)
        self.login_toggle = rumps.MenuItem("Start at Login", callback=self._toggle_login)
        self.menu = [
            self.status_item,
            None,
            self.ms_item,
            self.slack_item,
            None,
            self.t2s_item,
            self.s2t_item,
            None,
            self.pause_item,
            self.login_toggle,
            None,
            rumps.MenuItem("Settings…", callback=self._open_settings),
            rumps.MenuItem("Statuses…", callback=self._open_statuses),
            rumps.MenuItem("Setup Guide", callback=self._open_setup_guide),
            rumps.MenuItem("Open Logs…", callback=self._open_logs),
            rumps.MenuItem(f"Quit {constants.APP_NAME}", callback=self._quit),
        ]
        self._sync_toggle_states()

    def _sync_toggle_states(self) -> None:
        s = self.engine.settings
        self.t2s_item.state = s.teams_to_slack
        self.s2t_item.state = s.slack_to_teams
        self.pause_item.state = s.paused
        self.login_toggle.state = login_item.is_enabled()

    # Menu-bar icon
    def _render_icons(self) -> dict:
        try:
            from . import icons

            return icons.ensure_icons(os.path.join(constants.APP_SUPPORT_DIR, "icons"))
        except Exception:
            log.exception("menu-bar icon rendering unavailable; using text fallback")
            return {}

    def _apply_icon(self, state: HealthState) -> None:
        if state == self._icon_key:
            return
        if state is HealthState.OK:
            path, template = self._icons.get("template"), True  # system-tinted monochrome
        else:
            path, template = self._icons.get(state), False  # white glyph + coloured dot
        if path:
            self.template = template
            self.icon = path
            self.title = ""
        else:
            self.title = _FALLBACK_GLYPH[state]
        self._icon_key = state

    # Background sync worker
    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.engine.tick()
            except Exception:  # never let the worker die
                log.exception("sync tick failed")
            try:
                health = evaluate(self.engine)
                snapshot = {
                    "ms": self.engine.teams.is_connected(),
                    "slack": self.engine.slack.is_connected(),
                    "last_success": self.engine.last_success,
                }
            except Exception:
                log.exception("health evaluation failed")
                health, snapshot = self._health, self._snapshot
            with self._lock:
                self._health = health
                self._snapshot = snapshot
            self._stop.wait(max(self.engine.settings.poll_interval_seconds, 1))

    # Main-thread UI refresh
    def _refresh_ui(self, _timer) -> None:
        with self._lock:
            health = self._health
            snap = dict(self._snapshot)
        self._apply_icon(health.state)
        if snap.get("last_success"):
            line = f"{health.title} · {_ago(int(time.time() - snap['last_success']))}"
        else:
            line = health.title
        self.status_item.title = line
        self.ms_item.title = "Microsoft: Connected ✓" if snap.get("ms") else "Connect Microsoft…"
        self.slack_item.title = "Slack: Connected ✓" if snap.get("slack") else "Connect Slack…"
        if not self._onboarded:
            self._onboarded = True
            self._maybe_onboard()

    # Connect / disconnect
    def _on_ms_click(self, _item) -> None:
        if self.engine.teams.is_connected():
            if rumps.alert("Disconnect Microsoft?", "Stop reading your Teams presence?", ok="Disconnect", cancel="Cancel"):
                self.engine.teams.sign_out()
        else:
            self._connect_in_background(self.engine.teams.connect, "Microsoft")

    def _on_slack_click(self, _item) -> None:
        if self.engine.slack.is_connected():
            if rumps.alert("Disconnect Slack?", "Stop syncing your Slack status?", ok="Disconnect", cancel="Cancel"):
                self.engine.slack.sign_out()
        else:
            self._connect_in_background(lambda: connect_slack(self.engine.slack.secrets), "Slack")

    def _connect_in_background(self, fn, label: str) -> None:
        def task() -> None:
            try:
                fn()
                self._notify(f"{label} connected", "Syncing resumes automatically.")
            except PresenceSyncError as exc:
                self._notify(f"{label} sign-in failed", str(exc))
            except Exception as exc:
                log.exception("connect %s failed", label)
                self._notify(f"{label} sign-in failed", str(exc))

        threading.Thread(target=task, name=f"connect-{label}", daemon=True).start()

    # Toggles
    def _toggle_t2s(self, item) -> None:
        item.state = not item.state
        self.engine.settings.teams_to_slack = bool(item.state)
        self.engine.reconciler.settings.teams_to_slack = bool(item.state)
        self.engine.settings.save()

    def _toggle_s2t(self, item) -> None:
        item.state = not item.state
        self.engine.settings.slack_to_teams = bool(item.state)
        self.engine.reconciler.settings.slack_to_teams = bool(item.state)
        self.engine.settings.save()

    def _toggle_pause(self, item) -> None:
        item.state = not item.state
        self.engine.settings.paused = bool(item.state)
        self.engine.settings.save()

    def _toggle_login(self, item) -> None:
        try:
            if item.state:
                login_item.disable()
                item.state = False
            else:
                login_item.enable()
                item.state = True
        except Exception as exc:
            log.exception("toggle start-at-login failed")
            rumps.alert("Could not change Start at Login", str(exc))

    # Misc
    def set_direction(self, name: str, value: bool) -> None:
        """Update a sync direction from the Settings window and keep the menu in sync."""
        setattr(self.engine.settings, name, value)
        setattr(self.engine.reconciler.settings, name, value)
        self.engine.settings.save()
        (self.t2s_item if name == "teams_to_slack" else self.s2t_item).state = value

    def _open_settings(self, _item) -> None:
        try:
            from . import settings_window

            if self._settings_controller is None:
                self._settings_controller = settings_window.SettingsController.alloc().initWithApp_(self)
            self._settings_controller.show()
        except Exception:
            log.exception("could not open Settings")
            rumps.alert("Settings unavailable", "Could not open the Settings window.")

    def _open_statuses(self, _item) -> None:
        try:
            from . import settings_window

            if self._statuses_controller is None:
                self._statuses_controller = settings_window.StatusesController.alloc().initWithApp_(self)
            self._statuses_controller.show()
        except Exception:
            log.exception("could not open Statuses")
            rumps.alert("Statuses unavailable", "Could not open the Statuses window.")

    def _maybe_onboard(self) -> None:
        """First unconfigured launch → open Settings so setup is obvious."""
        try:
            if not self.engine.slack.is_connected() and not credentials.slack_client_id(self.engine.settings):
                self._open_settings(None)
        except Exception:
            log.exception("onboarding check failed")

    def _open_setup_guide(self, _item) -> None:
        path = constants.SETUP_GUIDE_PATH
        if os.path.exists(path):
            subprocess.run(["open", path], check=False)
        else:
            rumps.alert("Setup Guide not found", "The guide file is missing from the app bundle.")

    def _open_logs(self, _item) -> None:
        target = constants.LOG_PATH if os.path.exists(constants.LOG_PATH) else constants.APP_SUPPORT_DIR
        subprocess.run(["open", target], check=False)

    def _quit(self, _item) -> None:
        self._stop.set()
        rumps.quit_application()

    def _notify(self, title: str, message: str) -> None:
        try:
            rumps.notification(constants.APP_NAME, title, message)
        except Exception:
            log.info("notification: %s — %s", title, message)


def run_app() -> int:
    os.makedirs(constants.APP_SUPPORT_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        filename=constants.LOG_PATH,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not single_instance.acquire():
        log.info("PresenceSync is already running; this instance will exit")
        return 0
    # Menu-bar only — no Dock icon (matches the packaged .app's LSUIElement).
    NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    PresenceSyncApp().run()
    return 0
