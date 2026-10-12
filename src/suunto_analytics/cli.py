"""Command-line entry point (`suunto`): login, sync, status, reparse."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from pathlib import Path

from suunto_analytics.core.credentials import CredentialStore
from suunto_analytics.core.http_client import Cooldown, PoliteClientError
from suunto_analytics.core.repository import Database
from suunto_analytics.sources.suunto_app.runner import NeedsLogin, SuuntoolRunner, find_suuntool
from suunto_analytics.sources.suunto_app.sync import SOURCE, SyncService, reparse_cached

DATA = Path(os.environ.get("SUUNTO_DATA_DIR", "data"))


def _binary() -> Path:
    return find_suuntool() or sys.exit("suuntool binary not found; set SUUNTOOL_BIN (see README).")


def _runner(creds: CredentialStore) -> SuuntoolRunner:
    return SuuntoolRunner(_binary(), Cooldown(DATA / "cooldown.json"), creds)


def cmd_login(_: argparse.Namespace) -> None:
    creds = CredentialStore()
    email = input("Suunto email: ").strip()
    password = getpass.getpass("Password (not echoed): ")
    try:
        _runner(creds).login(email, password)
    except PoliteClientError as exc:
        sys.exit(f"Login stopped: {exc}")
    if input("Remember in macOS Keychain for silent re-login? [y/N] ").strip().lower() == "y":
        creds.save(email, password)
    print("Logged in.")


def cmd_sync(a: argparse.Namespace) -> None:
    creds = CredentialStore()
    runner = _runner(creds)
    try:
        counts = SyncService(runner, Database(DATA / "suunto.db"), DATA / "raw").sync(a.days)
    except NeedsLogin:
        print("Session expired and no stored credentials. Run: suunto login")
        sys.exit(4)
    except PoliteClientError as exc:
        print(f"Stopped: {exc}")
        sys.exit(1)
    print("Synced:", ", ".join(f"{k}={v}" for k, v in counts.items()), f"({runner.calls_made} calls)")


def cmd_reparse(_: argparse.Namespace) -> None:
    counts = reparse_cached(Database(DATA / "suunto.db"), DATA / "raw")
    print("Re-parsed from local cache (no network):", ", ".join(f"{k}={v}" for k, v in counts.items()))


def cmd_status(_: argparse.Namespace) -> None:
    db = Database(DATA / "suunto.db")
    for stream in ("sleep", "recovery", "activity", "workouts"):
        ts = db.last_ts(SOURCE, stream)
        print(f"{stream:10} last data: {time.strftime('%F %R', time.localtime(ts)) if ts else '-'}")
    until = Cooldown(DATA / "cooldown.json").until()
    print("cooldown:", time.strftime("%F %R", time.localtime(until)) if until > time.time() else "none")
    print("keychain credentials:", "saved" if CredentialStore().get() else "not saved")


def main() -> None:
    ap = argparse.ArgumentParser(prog="suunto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    s = sub.add_parser("sync")
    s.add_argument("--days", type=int, help="days to fetch (default: incremental, 7 on first run)")
    s.set_defaults(fn=cmd_sync)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("reparse", help="re-run parsers over data/raw without calling Suunto").set_defaults(fn=cmd_reparse)
    a = ap.parse_args()
    a.fn(a)
