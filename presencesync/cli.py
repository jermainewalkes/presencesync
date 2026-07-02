"""Headless CLI for the sync engine.

  python main.py --connect both | --once [--dry-run] | --status | --test
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .core import constants
from .core.engine import SyncEngine
from .core.errors import PresenceSyncError
from .core.factory import build_engine


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_status(engine: SyncEngine) -> None:
    ms = "connected" if engine.teams.is_connected() else "NOT connected"
    sl = "connected" if engine.slack.is_connected() else "NOT connected"
    print(f"  Microsoft: {ms}")
    print(f"  Slack:     {sl}")
    if not engine.teams.is_connected() or not engine.slack.is_connected():
        print("  → run `python main.py --connect both` to sign in.")


def _connect(engine: SyncEngine, which: str) -> None:
    from .core.oauth_slack import connect_slack

    if which in ("teams", "both"):
        print("Opening browser for Microsoft sign-in…")
        engine.teams.connect()
        print("  Microsoft connected ✓")
    if which in ("slack", "both"):
        print("Opening browser for Slack sign-in…")
        connect_slack(engine.slack.secrets)
        print("  Slack connected ✓")


def _summarize(result) -> None:
    if result.paused:
        print("Paused.")
        return
    t = f"{result.teams.activity} ({result.teams.availability})" if result.teams else "—"
    s = ("in huddle" if result.slack and result.slack.in_huddle else "no huddle") if result.slack else "—"
    print(f"Teams: {t}   Slack: {s}")
    for line in result.applied:
        print(f"  • {line}")
    if not result.applied:
        print(f"  • no change ({result.plan.slack_reason}; {result.plan.teams_reason})" if result.plan else "  • no change")
    for err in result.errors:
        print(f"  ! {err}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="presencesync", description="Teams ↔ Slack presence sync")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="plan only; make no API writes")
    parser.add_argument("--connect", choices=["slack", "teams", "both"], help="run OAuth sign-in and exit")
    parser.add_argument("--status", action="store_true", help="print connection status and exit")
    parser.add_argument("--test", action="store_true", help="test both connections (live) and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    engine = build_engine(dry_run=args.dry_run)

    if args.connect:
        try:
            _connect(engine, args.connect)
        except PresenceSyncError as exc:
            print(f"Connect failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.status:
        _print_status(engine)
        return 0

    if args.test:
        from .core.diagnostics import test_connections

        print(test_connections(engine))
        return 0

    _print_status(engine)

    if args.once:
        _summarize(engine.tick())
        return 0

    interval = engine.settings.poll_interval_seconds
    print(f"Syncing every {interval}s — Ctrl-C to stop.")
    try:
        while True:
            result = engine.tick()
            if result.applied or result.errors:
                _summarize(result)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0
