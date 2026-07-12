"""AppKit windows: Settings (credentials, connections, sync toggles) and Statuses."""

from __future__ import annotations

import logging
import threading

import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSBitmapImageFileTypePNG,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSFont,
    NSMenu,
    NSMenuItem,
    NSSecureTextField,
    NSSwitchButton,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

from ..core import constants, credentials

log = logging.getLogger(__name__)

# Layout
W = 500
PAD = 24
LBL_W = 104
FLD_X = PAD + LBL_W + 8
FLD_W = W - FLD_X - PAD
ROW = 24
BTN_W = 150


def _rect(x, y, w, h):
    return ((float(x), float(y)), (float(w), float(h)))


def _label(text, x, y, w, *, bold=False, secondary=False, size=13):
    f = NSTextField.labelWithString_(text)
    f.setFrame_(_rect(x, y, w, ROW))
    f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size))
    if secondary:
        f.setTextColor_(NSColor.secondaryLabelColor())
    return f


def _field(value, x, y, w, *, secure=False, placeholder=""):
    cls = NSSecureTextField if secure else NSTextField
    f = cls.alloc().initWithFrame_(_rect(x, y, w, ROW))
    f.setStringValue_(value or "")
    if placeholder:
        f.setPlaceholderString_(placeholder)
    return f


def _button(title, x, y, w, target, action):
    b = NSButton.buttonWithTitle_target_action_(title, target, action)
    b.setFrame_(_rect(x, y - 2, w, ROW + 4))
    b.setBezelStyle_(NSBezelStyleRounded)
    return b


def _checkbox(title, x, y, w, state, target, action):
    b = NSButton.alloc().initWithFrame_(_rect(x, y, w, ROW))
    b.setButtonType_(NSSwitchButton)
    b.setTitle_(title)
    b.setState_(1 if state else 0)
    b.setTarget_(target)
    b.setAction_(action)
    return b


def _separator(y):
    box = NSBox.alloc().initWithFrame_(_rect(PAD, y, W - 2 * PAD, 1))
    box.setBoxType_(NSBoxSeparator)
    return box


def _ensure_edit_menu():
    """Menu-bar (accessory) apps have no Edit menu, so Cut/Copy/Paste key equivalents
    (Cmd-X/C/V) aren't wired to the responder chain. Install a minimal one so the text
    fields support Cmd-V etc."""
    app = NSApplication.sharedApplication()
    main = app.mainMenu()
    if main is None:
        main = NSMenu.alloc().init()
        app.setMainMenu_(main)
    for i in range(main.numberOfItems()):
        sub = main.itemAtIndex_(i).submenu()
        if sub is not None and sub.title() == "Edit":
            return
    item = NSMenuItem.alloc().init()
    main.addItem_(item)
    edit = NSMenu.alloc().initWithTitle_("Edit")
    item.setSubmenu_(edit)
    for title, action, key in (
        ("Cut", "cut:", "x"),
        ("Copy", "copy:", "c"),
        ("Paste", "paste:", "v"),
        ("Select All", "selectAll:", "a"),
    ):
        edit.addItem_(NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key))


class SettingsController(NSObject):
    def initWithApp_(self, app):
        self = objc.super(SettingsController, self).init()
        if self is None:
            return None
        self._app = app
        self.window = None
        self._f = {}
        return self

    # Data access (works with or without a running app)
    @objc.python_method
    def _settings(self):
        if self._app is not None:
            return self._app.engine.settings
        from ..core.store import Settings

        return Settings.load()

    @objc.python_method
    def _secrets(self):
        if self._app is not None:
            return self._app.engine.slack.secrets
        from ..core.store import SecretStore

        return SecretStore()

    @objc.python_method
    def _connected(self, which):
        if self._app is None:
            return False
        return (self._app.engine.teams if which == "teams" else self._app.engine.slack).is_connected()

    # Build
    @objc.python_method
    def _build(self):
        s = self._settings()
        secret_set = bool(self._secrets().get_slack_client_secret())
        H = 614
        view = NSView.alloc().initWithFrame_(_rect(0, 0, W, H))
        add = view.addSubview_

        y = [H - PAD - ROW]

        def row(gap=10):
            yy = y[0]
            y[0] -= ROW + gap
            return yy

        def header(text):
            y[0] -= 6
            yy = row(gap=8)
            add(_label(text, PAD, yy, W - 2 * PAD, bold=True))
            return yy

        add(_label("PresenceSync Settings", PAD, row(gap=4), W - 2 * PAD, bold=True, size=15))

        # Microsoft
        header("Microsoft (Teams)")
        yy = row()
        add(_label("Tenant ID", PAD, yy, LBL_W))
        self._f["ms_tenant"] = _field(s.ms_tenant_id or credentials.ms_tenant_id(s), FLD_X, yy, FLD_W)
        add(self._f["ms_tenant"])
        yy = row()
        add(_label("Client ID", PAD, yy, LBL_W))
        self._f["ms_client"] = _field(s.ms_client_id or credentials.ms_client_id(s), FLD_X, yy, FLD_W)
        add(self._f["ms_client"])
        yy = row(gap=14)
        self._f["ms_status"] = _label(self._status_text("teams"), PAD, yy, W - 2 * PAD - BTN_W - 8, secondary=True)
        add(self._f["ms_status"])
        add(_button("Connect / Reconnect", W - PAD - BTN_W, yy, BTN_W, self, "connectMS:"))

        add(_separator(y[0] + ROW))

        # Slack
        header("Slack")
        yy = row()
        add(_label("Client ID", PAD, yy, LBL_W))
        self._f["slack_id"] = _field(s.slack_client_id or credentials.slack_client_id(s), FLD_X, yy, FLD_W)
        add(self._f["slack_id"])
        yy = row()
        add(_label("Client Secret", PAD, yy, LBL_W))
        self._f["slack_secret"] = _field(
            "", FLD_X, yy, FLD_W, secure=True,
            placeholder="•••••••• (saved)" if secret_set else "Slack client secret",
        )
        add(self._f["slack_secret"])
        yy = row(gap=14)
        self._f["slack_status"] = _label(self._status_text("slack"), PAD, yy, W - 2 * PAD - BTN_W - 8, secondary=True)
        add(self._f["slack_status"])
        add(_button("Connect / Reconnect", W - PAD - BTN_W, yy, BTN_W, self, "connectSlack:"))

        add(_separator(y[0] + ROW))

        # Sync directions
        header("Sync")
        yy = row()
        add(_checkbox("Teams → Slack", PAD, yy, (W - 2 * PAD) / 2, s.teams_to_slack, self, "toggleT2S:"))
        add(_checkbox("Slack → Teams", PAD + (W - 2 * PAD) / 2, yy, (W - 2 * PAD) / 2, s.slack_to_teams, self, "toggleS2T:"))
        yy = row(gap=16)
        add(_checkbox("Check for Updates Automatically", PAD, yy, W - 2 * PAD, s.auto_check_updates, self, "toggleAutoUpdate:"))

        add(_separator(y[0] + ROW - 2))

        # Diagnostics
        header("Diagnostics")
        yy = row(gap=8)
        add(_button("Test Connection", PAD, yy, BTN_W, self, "testConnection:"))
        res_h = 2 * ROW
        res_y = yy - res_h - 6
        results = NSTextField.wrappingLabelWithString_("")
        results.setFrame_(_rect(PAD, res_y, W - 2 * PAD, res_h))
        results.setTextColor_(NSColor.secondaryLabelColor())
        self._f["test_results"] = results
        add(results)

        # Bottom buttons
        by = res_y - ROW - 12
        add(_button("Setup Guide", PAD, by, 118, self, "openGuide:"))
        add(_button("Save", W - PAD - 90, by, 90, self, "save:"))
        add(_button("Close", W - PAD - 90 - 8 - 90, by, 90, self, "close:"))

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _rect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("PresenceSync Settings")
        win.setContentView_(view)
        win.setReleasedWhenClosed_(False)  # so we can reopen the same controller
        win.center()
        self.window = win

    @objc.python_method
    def _status_text(self, which):
        label = "Microsoft" if which == "teams" else "Slack"
        return f"{label}: Connected ✓" if self._connected(which) else f"{label}: Not Connected"

    # Presentation
    @objc.python_method
    def show(self):
        _ensure_edit_menu()
        if self.window is None:
            self._build()
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    @objc.python_method
    def _refresh_status(self):
        if "ms_status" in self._f:
            self._f["ms_status"].setStringValue_(self._status_text("teams"))
            self._f["slack_status"].setStringValue_(self._status_text("slack"))

    # Actions (selectors)
    @objc.python_method
    def _save(self):
        s = self._settings()
        old = (s.ms_tenant_id, s.ms_client_id)
        s.ms_tenant_id = self._f["ms_tenant"].stringValue().strip()
        s.ms_client_id = self._f["ms_client"].stringValue().strip()
        s.slack_client_id = self._f["slack_id"].stringValue().strip()
        secret = self._f["slack_secret"].stringValue()
        if secret:
            self._secrets().set_slack_client_secret(secret)
            self._f["slack_secret"].setStringValue_("")
            self._f["slack_secret"].setPlaceholderString_("•••••••• (saved)")
        s.save()
        if self._app is not None and (s.ms_tenant_id, s.ms_client_id) != old:
            from ..core.teams_client import TeamsClient

            self._app.engine.teams = TeamsClient(s)  # rebuild MSAL with new identity

    def save_(self, sender):
        self._save()
        self._refresh_status()

    def connectMS_(self, sender):
        self._save()
        if self._app is not None:
            self._app._connect_in_background(self._app.engine.teams.connect, "Microsoft")

    def connectSlack_(self, sender):
        self._save()
        if self._app is not None:
            from ..core.oauth_slack import connect_slack

            eng = self._app.engine
            self._app._connect_in_background(lambda: connect_slack(eng.slack.secrets, eng.settings), "Slack")

    def toggleT2S_(self, sender):
        if self._app is not None:
            self._app.set_direction("teams_to_slack", bool(sender.state()))

    def toggleS2T_(self, sender):
        if self._app is not None:
            self._app.set_direction("slack_to_teams", bool(sender.state()))

    def toggleAutoUpdate_(self, sender):
        s = self._settings()
        s.auto_check_updates = bool(sender.state())
        s.save()

    def close_(self, sender):
        if self.window is not None:
            self.window.close()

    def openGuide_(self, sender):
        import os
        import subprocess

        from ..core import constants

        if os.path.exists(constants.SETUP_GUIDE_PATH):
            subprocess.run(["open", constants.SETUP_GUIDE_PATH], check=False)

    def testConnection_(self, sender):
        self._f["test_results"].setStringValue_("Testing…")
        if self._app is None:
            return
        engine = self._app.engine

        def work():
            from ..core import diagnostics

            try:
                text = diagnostics.test_connections(engine)
            except Exception as exc:  # never crash the UI on a test
                text = f"Test failed: {exc}"
            self.performSelectorOnMainThread_withObject_waitUntilDone_("showTestResult:", text, False)

        threading.Thread(target=work, name="test-connection", daemon=True).start()

    def showTestResult_(self, text):
        self._f["test_results"].setStringValue_(text)


class StatusesController(NSObject):
    """Edit the Slack status text/emoji per Teams-presence category, and the message
    put on Teams while you're in a Slack huddle."""

    def initWithApp_(self, app):
        self = objc.super(StatusesController, self).init()
        if self is None:
            return None
        self._app = app
        self.window = None
        self._f = {}
        return self

    @objc.python_method
    def _settings(self):
        if self._app is not None:
            return self._app.engine.settings
        from ..core.store import Settings

        return Settings.load()

    @objc.python_method
    def _build(self):
        s = self._settings()
        overrides = s.status_map or {}
        cats = constants.STATUS_CATEGORIES
        lbl_w = 92
        tx = PAD + lbl_w + 8
        tx_w = 214
        ex = tx + tx_w + 8
        ex_w = W - ex - PAD

        H = 398
        view = NSView.alloc().initWithFrame_(_rect(0, 0, W, H))
        add = view.addSubview_
        y = [H - PAD - ROW]

        def row(gap=10):
            yy = y[0]
            y[0] -= ROW + gap
            return yy

        def header(text):
            y[0] -= 6
            yy = row(gap=8)
            add(_label(text, PAD, yy, W - 2 * PAD, bold=True))
            return yy

        add(_label("Slack Statuses", PAD, row(gap=6), W - 2 * PAD, bold=True, size=15))

        header("Your Slack status when Teams shows…")
        yy = row(gap=2)
        add(_label("Status Text", tx, yy, tx_w, secondary=True, size=11))
        add(_label("Emoji", ex, yy, ex_w, secondary=True, size=11))
        for cat in cats:
            yy = row()
            add(_label(cat.label, PAD, yy, lbl_w))
            o = overrides.get(cat.key, {})
            tf = _field(o.get("text", cat.text), tx, yy, tx_w)
            ef = _field(o.get("emoji", cat.emoji), ex, yy, ex_w, placeholder=":emoji:")
            self._f[cat.key + "_text"] = tf
            self._f[cat.key + "_emoji"] = ef
            add(tf)
            add(ef)

        add(_separator(y[0] + ROW))
        header("Teams status when you're in a Slack huddle")
        yy = row()
        hm = _field(s.huddle_message or constants.HUDDLE_TEAMS_MESSAGE, PAD, yy, W - 2 * PAD)
        self._f["huddle_message"] = hm
        add(hm)

        y[0] -= 6
        by = row(gap=0)
        add(_button("Save", W - PAD - 90, by, 90, self, "save:"))
        add(_button("Close", W - PAD - 90 - 8 - 90, by, 90, self, "close:"))

        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            _rect(0, 0, W, H),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False,
        )
        win.setTitle_("PresenceSync Statuses")
        win.setContentView_(view)
        win.setReleasedWhenClosed_(False)
        win.center()
        self.window = win

    @objc.python_method
    def show(self):
        _ensure_edit_menu()
        if self.window is None:
            self._build()
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def save_(self, sender):
        s = self._settings()
        status_map = {}
        for cat in constants.STATUS_CATEGORIES:
            status_map[cat.key] = {
                "text": self._f[cat.key + "_text"].stringValue().strip(),
                "emoji": self._f[cat.key + "_emoji"].stringValue().strip(),
            }
        s.status_map = status_map
        s.huddle_message = self._f["huddle_message"].stringValue().strip()
        s.save()
        if self._app is not None:
            self._app.engine.reconciler.settings = s.to_sync_settings()
        if self.window is not None:
            self.window.close()

    def close_(self, sender):
        if self.window is not None:
            self.window.close()


def render_statuses_preview(path: str) -> None:
    NSApplication.sharedApplication()
    controller = StatusesController.alloc().initWithApp_(None)
    controller._build()
    view = controller.window.contentView()
    view.setWantsLayer_(True)
    view.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(path, True)
    print(f"wrote {path}")


def render_preview(path: str) -> None:
    """Render the window content to a PNG for design review (no app needed)."""
    NSApplication.sharedApplication()
    controller = SettingsController.alloc().initWithApp_(None)
    controller._build()
    view = controller.window.contentView()
    view.setWantsLayer_(True)
    view.layer().setBackgroundColor_(NSColor.windowBackgroundColor().CGColor())
    rep = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), rep)
    rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(path, True)
    print(f"wrote {path}")


if __name__ == "__main__":
    import sys

    render_preview(sys.argv[1] if len(sys.argv) > 1 else "/tmp/presencesync-settings.png")
    render_statuses_preview("/tmp/presencesync-statuses.png")
