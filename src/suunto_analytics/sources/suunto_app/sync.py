"""Incremental sync: suuntool -> raw cache (0600) -> parsers -> SQLite. Idempotent."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from suunto_analytics.core.repository import Database
from suunto_analytics.sources.suunto_app import parsers as p
from suunto_analytics.sources.suunto_app.runner import NotFound, SuuntoolRunner

SOURCE = "suunto_app"
STREAMS = {  # stream -> (parser, table, timestamp column)
    "sleep": (p.parse_sleep, "sleep_nights", "start_ts"),
    "sleepstages": (p.parse_sleep_stages, "sleep_stages", "start_ts"),
    "recovery": (p.parse_recovery, "recovery_samples", "ts"),
    "activity": (p.parse_activity_samples, "activity_samples", "ts"),
}


class SyncService:
    def __init__(self, runner: SuuntoolRunner, db: Database, raw_dir: Path, *,
                 default_days: int = 7, max_backfill_days: int = 30, max_fit_per_run: int = 10,
                 now: float | None = None):
        self._r, self._db, self._raw = runner, db, raw_dir
        self._days, self._max_back, self._max_fit = default_days, max_backfill_days, max_fit_per_run
        self._now = now

    def _since(self, last_ts: int, days: int | None) -> str:
        now = self._now or time.time()
        floor = now - self._max_back * 86400
        start = (last_ts - 86400) if last_ts and days is None else now - (days or self._days) * 86400
        return datetime.fromtimestamp(max(start, floor)).strftime("%Y-%m-%d")

    def _out(self, name: str) -> Path:
        self._raw.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._raw / name
        path.touch(mode=0o600)
        os.chmod(path, 0o600)
        return path

    def sync(self, days: int | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for stream, (parse, table, col) in STREAMS.items():
            since = self._since(self._db.last_ts(SOURCE, stream), days)
            out = self._out(f"{stream}.ndjson")
            self._r.call(["wellness", stream, "--since", since, "-o", str(out)])
            rows = list(parse(json.loads(l) for l in out.read_text().splitlines() if l.strip()))
            counts[stream] = self._db.upsert(table, rows)
            if rows:
                self._db.set_last_ts(SOURCE, stream, max(r[col] for r in rows))
        counts["workouts"] = self._sync_workouts(days)
        out = self._out("settings.json")
        self._r.call(["profile", "settings", "-o", str(out)])
        counts["profile"] = self._db.upsert("user_profile", p.parse_profile(json.loads(out.read_text())))
        return counts

    def _sync_workouts(self, days: int | None) -> int:
        since = self._since(self._db.last_ts(SOURCE, "workouts"), days)
        out = self._out("workouts.json")
        self._r.call(["workouts", "list", "--since", since, "--limit", "100", "-o", str(out)])
        rows = list(p.parse_workouts_json(json.loads(out.read_text())))
        n = self._db.upsert("activities", rows)
        if rows:
            self._db.set_last_ts(SOURCE, "workouts", max(r["start_ts"] for r in rows))
        todo = [k for (k,) in self._db.query(
            "SELECT key FROM activities WHERE has_fit=0 AND source=? ORDER BY start_ts DESC LIMIT ?",
            (SOURCE, self._max_fit))]
        for key in todo:
            fit = self._out(f"workout_{key}.fit")
            try:
                self._r.call(["workouts", "fit", key, "-o", str(fit)])
            except NotFound:
                self._db.mark_no_fit(key)
                continue
            try:
                d = p.parse_fit(fit, key)
            except Exception:  # corrupt/unsupported FIT: don't abort the run or retry forever
                fit.unlink(missing_ok=True)
                self._db.mark_no_fit(key)
                continue
            store_fit(self._db, d)
        return n


def store_fit(db: Database, d: dict) -> None:
    db.upsert("activities", [{**d["activity"], "source": SOURCE}])
    db.upsert("activity_laps", d["laps"])
    db.upsert("activity_records", d["records"])


def reparse_cached(db: Database, raw_dir: Path) -> dict[str, int]:
    """Re-run the parsers over the local raw cache (no network) after a parser change."""
    counts = {"workouts": 0, "fit": 0, "fit_failed": 0, "profile": 0}
    settings = raw_dir / "settings.json"
    if settings.exists():
        counts["profile"] = db.upsert("user_profile", p.parse_profile(json.loads(settings.read_text())))
    listing = raw_dir / "workouts.json"
    if listing.exists():
        counts["workouts"] = db.upsert("activities", p.parse_workouts_json(json.loads(listing.read_text())))
    for fit in sorted(raw_dir.glob("workout_*.fit")):
        key = fit.stem.removeprefix("workout_")
        if not db.query("SELECT 1 FROM activities WHERE key=?", (key,)):
            continue
        try:
            store_fit(db, p.parse_fit(fit, key))
            counts["fit"] += 1
        except Exception:  # keep going; a bad file must not block the others
            counts["fit_failed"] += 1
    return counts
