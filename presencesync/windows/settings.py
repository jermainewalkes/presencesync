"""tkinter dialogs: Settings (credentials, connections, diagnostics) and Statuses.

Each dialog runs a fresh Tk root in its own thread so it can coexist with the
pystray event loop; only one dialog of each kind opens at a time.
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import ttk

from ..core import constants, credentials, diagnostics

log = logging.getLogger(__name__)

_open_dialogs: set[str] = set()
_lock = threading.Lock()


def _launch(kind: str, target, app) -> None:
    with _lock:
        if kind in _open_dialogs:
            return
        _open_dialogs.add(kind)

    def run():
        try:
            target(app)
        except Exception:
            log.exception("%s dialog failed", kind)
        finally:
            with _lock:
                _open_dialogs.discard(kind)

    threading.Thread(target=run, name=f"dialog-{kind}", daemon=True).start()


def open_settings(app) -> None:
    _launch("settings", _settings_dialog, app)


def open_statuses(app) -> None:
    _launch("statuses", _statuses_dialog, app)


def _make_root(title: str) -> tk.Tk:
    root = tk.Tk()
    root.title(title)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    frame = ttk.Frame(root, padding=16)
    frame.grid(sticky="nsew")
    root._frame = frame
    return root


def _settings_dialog(app) -> None:
    s = app.engine.settings
    secrets = app.engine.slack.secrets
    root = _make_root("PresenceSync Settings")
    f = root._frame

    fields = {}

    def add_field(row, label, value, show=None):
        ttk.Label(f, text=label).grid(row=row, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=value)
        entry = ttk.Entry(f, textvariable=var, width=44, show=show or "")
        entry.grid(row=row, column=1, columnspan=2, sticky="we", pady=3)
        return var

    ttk.Label(f, text="Microsoft (Teams)", font=("", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
    fields["ms_tenant_id"] = add_field(1, "Tenant ID", s.ms_tenant_id)
    fields["ms_client_id"] = add_field(2, "Client ID", s.ms_client_id)
    ms_status = ttk.Label(f, text="")
    ms_status.grid(row=3, column=0, columnspan=2, sticky="w")
    ttk.Button(f, text="Connect / Reconnect", command=lambda: (save(), app.connect_microsoft())).grid(row=3, column=2, sticky="e")

    ttk.Separator(f).grid(row=4, column=0, columnspan=3, sticky="we", pady=8)
    ttk.Label(f, text="Slack", font=("", 10, "bold")).grid(row=5, column=0, columnspan=3, sticky="w")
    fields["slack_client_id"] = add_field(6, "Client ID", s.slack_client_id)
    secret_placeholder = "(saved)" if secrets.get_slack_client_secret() else ""
    fields["slack_secret"] = add_field(7, "Client Secret", secret_placeholder, show="*")
    slack_status = ttk.Label(f, text="")
    slack_status.grid(row=8, column=0, columnspan=2, sticky="w")
    ttk.Button(f, text="Connect / Reconnect", command=lambda: (save(), app.connect_slack())).grid(row=8, column=2, sticky="e")

    ttk.Separator(f).grid(row=9, column=0, columnspan=3, sticky="we", pady=8)
    t2s = tk.BooleanVar(value=s.teams_to_slack)
    s2t = tk.BooleanVar(value=s.slack_to_teams)
    ttk.Checkbutton(f, text="Sync Teams to Slack", variable=t2s,
                    command=lambda: app.set_direction("teams_to_slack", t2s.get())).grid(row=10, column=0, sticky="w")
    ttk.Checkbutton(f, text="Sync Slack to Teams", variable=s2t,
                    command=lambda: app.set_direction("slack_to_teams", s2t.get())).grid(row=10, column=1, sticky="w")

    ttk.Separator(f).grid(row=11, column=0, columnspan=3, sticky="we", pady=8)
    result = ttk.Label(f, text="", wraplength=420, justify="left")
    result.grid(row=13, column=0, columnspan=3, sticky="w", pady=(4, 8))

    def refresh_status():
        ms_status.config(text="Microsoft: Connected" if app.engine.teams.is_connected() else "Microsoft: Not Connected")
        slack_status.config(text="Slack: Connected" if app.engine.slack.is_connected() else "Slack: Not Connected")
        root.after(2000, refresh_status)

    def save():
        s.ms_tenant_id = fields["ms_tenant_id"].get().strip()
        s.ms_client_id = fields["ms_client_id"].get().strip()
        s.slack_client_id = fields["slack_client_id"].get().strip()
        secret = fields["slack_secret"].get().strip()
        if secret and secret != "(saved)":
            secrets.set_slack_client_secret(secret)
            fields["slack_secret"].set("(saved)")
        s.save()
        app.rebuild_teams_client()

    test_result: "queue.Queue[str]" = queue.Queue()

    def poll_test_result():
        try:
            text = test_result.get_nowait()
        except queue.Empty:
            root.after(150, poll_test_result)
        else:
            result.config(text=text)

    def work():
        try:
            test_result.put(diagnostics.test_connections(app.engine))
        except Exception as exc:
            log.exception("connection test failed")
            test_result.put(f"Test failed: {exc}")

    def test():
        result.config(text="Testing...")
        threading.Thread(target=work, daemon=True).start()
        root.after(150, poll_test_result)

    ttk.Button(f, text="Test Connection", command=test).grid(row=12, column=0, sticky="w")
    ttk.Button(f, text="Setup Guide", command=open_guide).grid(row=14, column=0, sticky="w")
    ttk.Button(f, text="Save", command=save).grid(row=14, column=2, sticky="e")
    ttk.Button(f, text="Close", command=root.destroy).grid(row=14, column=1, sticky="e")

    refresh_status()
    root.mainloop()


def _statuses_dialog(app) -> None:
    s = app.engine.settings
    overrides = s.status_map or {}
    root = _make_root("PresenceSync Statuses")
    f = root._frame

    ttk.Label(f, text="Your Slack status when Teams shows...", font=("", 10, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
    ttk.Label(f, text="Status Text").grid(row=1, column=1, sticky="w")
    ttk.Label(f, text="Emoji").grid(row=1, column=2, sticky="w")

    rows = {}
    for i, cat in enumerate(constants.STATUS_CATEGORIES, start=2):
        o = overrides.get(cat.key, {})
        ttk.Label(f, text=cat.label).grid(row=i, column=0, sticky="w", pady=3)
        text = tk.StringVar(value=o.get("text", cat.text))
        emoji = tk.StringVar(value=o.get("emoji", cat.emoji))
        ttk.Entry(f, textvariable=text, width=28).grid(row=i, column=1, sticky="we", padx=(6, 6))
        ttk.Entry(f, textvariable=emoji, width=20).grid(row=i, column=2, sticky="we")
        rows[cat.key] = (text, emoji)

    row = len(constants.STATUS_CATEGORIES) + 2
    ttk.Separator(f).grid(row=row, column=0, columnspan=3, sticky="we", pady=8)
    ttk.Label(f, text="Teams status when you're in a Slack huddle", font=("", 10, "bold")).grid(
        row=row + 1, column=0, columnspan=3, sticky="w")
    huddle = tk.StringVar(value=s.huddle_message or constants.HUDDLE_TEAMS_MESSAGE)
    ttk.Entry(f, textvariable=huddle, width=56).grid(row=row + 2, column=0, columnspan=3, sticky="we", pady=4)

    def save():
        s.status_map = {k: {"text": t.get().strip(), "emoji": e.get().strip()} for k, (t, e) in rows.items()}
        s.huddle_message = huddle.get().strip()
        s.save()
        app.engine.reconciler.settings = s.to_sync_settings()
        root.destroy()

    ttk.Button(f, text="Close", command=root.destroy).grid(row=row + 3, column=1, sticky="e", pady=(8, 0))
    ttk.Button(f, text="Save", command=save).grid(row=row + 3, column=2, sticky="e", pady=(8, 0))
    root.mainloop()


def open_guide() -> None:
    path = constants.SETUP_GUIDE_PATH
    if os.path.exists(path):
        os.startfile(path)  # noqa: attribute exists on Windows


def open_logs() -> None:
    target = constants.LOG_PATH if os.path.exists(constants.LOG_PATH) else constants.APP_SUPPORT_DIR
    subprocess.run(["explorer", "/select,", target] if os.path.exists(constants.LOG_PATH) else ["explorer", target], check=False)
