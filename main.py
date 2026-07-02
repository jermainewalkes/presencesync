#!/usr/bin/env python3
"""Entry point.

  python main.py [--once] [--dry-run] [--connect both] [--status] [--test]  # headless CLI
  python main.py --app                                                      # tray/menu-bar app

With no arguments, launches the platform app if available, else the headless loop.
"""

import sys

HEADLESS_FLAGS = {"--once", "--dry-run", "--connect", "--status", "--test", "-v", "--verbose"}


def _run_platform_app():
    if sys.platform == "darwin":
        from presencesync.macos.app import run_app
    elif sys.platform == "win32":
        from presencesync.windows.app import run_app
    else:
        raise RuntimeError(f"no app front end for platform {sys.platform!r}")
    return run_app()


def main() -> int:
    argv = sys.argv[1:]
    wants_app = "--app" in argv
    wants_headless = any(a in HEADLESS_FLAGS or a.startswith("--connect") for a in argv)

    if wants_app or not wants_headless:
        try:
            return _run_platform_app()
        except Exception as exc:
            if wants_app:
                print(f"App unavailable: {exc}", file=sys.stderr)
                return 1
            from presencesync.cli import main as cli_main

            return cli_main([a for a in argv if a != "--app"])

    from presencesync.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
