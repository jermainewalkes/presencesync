"""py2app build config — produces PresenceSync.app (the final packaging step).

Build:
    ./venv/bin/pip install py2app
    ./venv/bin/python setup.py py2app
    open dist/PresenceSync.app

The build is unsigned (fine for your own Mac — right-click → Open the first time).
Code-signing + notarization is the later rollout step (see README → Rollout).
"""

from setuptools import setup

from presencesync import __version__

APP = ["main.py"]
DATA_FILES = ["resources/setup_guide.html"]

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "PresenceSync",
        "CFBundleDisplayName": "PresenceSync",
        "CFBundleIdentifier": "com.jermainewalkes.presencesync",
        "CFBundleVersion": __version__,
        "CFBundleShortVersionString": __version__,
        # Menu-bar only — no Dock icon, no app-switcher entry.
        "LSUIElement": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "",
    },
    "packages": [
        "presencesync",
        "rumps",
        "msal",
        "msal_extensions",
        "requests",
        "keyring",
        "certifi",
    ],
    # Ensure the macOS Keychain backend is bundled (it's discovered dynamically).
    "includes": ["keyring.backends.macOS"],
    "iconfile": "resources/PresenceSync.icns",
}

setup(
    app=APP,
    name="PresenceSync",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
