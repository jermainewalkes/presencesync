# Contributing to PresenceSync

Thanks for taking an interest. PresenceSync is a small, focused menu-bar / system-tray
app that keeps Microsoft Teams presence and Slack status in sync. Bug reports, fixes and
well-scoped features are all welcome.

## Getting set up

You need Python 3.11 or newer.

```bash
git clone https://github.com/jermainewalkes/presencesync.git
cd presencesync
bash setup.command        # macOS  (or setup.bat on Windows)
```

`setup.command` / `setup.bat` create a virtual environment, install dependencies and
launch the app. To set up without launching, do it by hand:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

You do not need real Microsoft or Slack credentials to develop or run the tests — the
suite is fully mocked.

## Running the tests

```bash
./venv/bin/python -m unittest discover -s tests -v   # 46 tests, no network needed
```

The tests must pass before a change is merged. If you touch the platform front end you
cannot run on this machine (the Windows tray app on macOS, or vice versa), compile-check
it instead:

```bash
./venv/bin/python -m py_compile presencesync/windows/app.py presencesync/windows/settings.py
```

## How the code is laid out

- `presencesync/core/` — the engine, reconciler, API clients, OAuth, storage and health
  logic. This is platform-independent and is where most logic and all tests live.
- `presencesync/macos/` — the rumps menu-bar front end.
- `presencesync/windows/` — the pystray system-tray front end.

Please keep new behaviour in `core/` with tests, and keep the platform folders thin. The
two sync directions are deliberately built so they cannot feed each other — if you change
anything in `core/sync.py`, add or update a case in `tests/test_sync.py` to prove the loop
prevention still holds.

## Style

- Comments and docstrings: minimum necessary, concise and professional. No emojis in code.
  Prefer self-explanatory code over commentary.
- British spelling and punctuation in prose (no serial comma).
- User-facing labels and buttons use Title Case ("Test Connection"); prose, headings and
  status readouts stay sentence case.

## Submitting a change

1. Branch from `main`.
2. Make the change, keep the diff focused, and add tests where it makes sense.
3. Run the test suite and confirm it is green.
4. Open a pull request with a clear description of what changed and why. The PR template
   will prompt you for the essentials.

## Reporting bugs and requesting features

Use the issue templates — they ask for the platform, app version and the steps to
reproduce, which is usually all that is needed to get started. For anything
security-related, please follow [SECURITY.md](SECURITY.md) rather than opening a public
issue.

## Licence

By contributing you agree that your contribution is licensed under the project's
[MIT licence](LICENSE).
