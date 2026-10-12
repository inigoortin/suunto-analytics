"""SQLite repository: idempotent upserts (parameterized SQL only) and read-only access."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path

from suunto_analytics.core.schema import ADDED_COLUMNS, SCHEMA

# table -> (primary-key columns, all writable columns); the allow-list keeps SQL parameterized
# and column names out of caller control.
TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "activities": (
        ("key",),
        (
            "key",
            "source",
            "start_ts",
            "end_ts",
            "sport",
            "duration_s",
            "elapsed_s",
            "distance_m",
            "ascent_m",
            "descent_m",
            "hr_min",
            "hr_avg",
            "hr_max",
            "avg_speed_ms",
            "max_speed_ms",
            "calories",
            "tss",
            "training_effect",
            "peak_epoc",
            "vo2max_est",
            "recovery_time_s",
            "avg_power",
            "norm_power",
            "avg_cadence",
            "hr_zone_s",
            "has_fit",
            "hr_zone_bounds",
            "user_max_hr",
        ),
    ),
    "activity_laps": (
        ("activity_key", "idx"),
        (
            "activity_key",
            "idx",
            "start_ts",
            "duration_s",
            "distance_m",
            "hr_avg",
            "hr_max",
            "avg_speed_ms",
            "avg_power",
            "avg_cadence",
        ),
    ),
    "activity_records": (
        ("activity_key", "ts"),
        (
            "activity_key",
            "ts",
            "distance_m",
            "hr",
            "speed_ms",
            "altitude_m",
            "cadence",
            "power",
            "lat",
            "lon",
        ),
    ),
    "sleep_nights": (
        ("sleep_id",),
        (
            "sleep_id",
            "start_ts",
            "is_nap",
            "duration_s",
            "deep_s",
            "light_s",
            "rem_s",
            "awake_s",
            "hr_avg_bpm",
            "hr_min_bpm",
            "hrv_avg_ms",
            "spo2_max",
            "quality",
        ),
    ),
    "sleep_stages": (("start_ts",), ("start_ts", "stage", "duration_s")),
    "recovery_samples": (("ts",), ("ts", "balance", "stress_state")),
    "activity_samples": (("ts",), ("ts", "hr_bpm", "steps", "energy_kcal")),
    "user_profile": (("key",), ("key", "value")),
}


class Database:
    def __init__(self, path: Path | str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns introduced after a DB was created (SQLite has no ADD COLUMN IF NOT EXISTS)."""
        with self._conn:
            for table, col, typ in ADDED_COLUMNS:
                have = {r[1] for r in self._conn.execute(f"PRAGMA table_info({table})")}
                if col not in have:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")

    def upsert(self, table: str, rows: Iterable[Mapping[str, object]]) -> int:
        """Insert or update rows by primary key; unknown columns raise. Returns rows written."""
        if table not in TABLES:
            raise ValueError(f"unknown table {table!r}")
        pk, cols = TABLES[table]
        n = 0
        with self._conn:
            for row in rows:
                extra = set(row) - set(cols)
                if extra:
                    raise ValueError(f"unknown columns for {table}: {sorted(extra)}")
                keys = [c for c in cols if c in row]
                updates = [c for c in keys if c not in pk]
                sql = (
                    f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))}) "
                    f"ON CONFLICT({', '.join(pk)}) DO "
                    + (
                        f"UPDATE SET {', '.join(f'{c}=excluded.{c}' for c in updates)}"
                        if updates
                        else "NOTHING"
                    )
                )
                self._conn.execute(sql, [row[c] for c in keys])
                n += 1
        return n

    def last_ts(self, source: str, stream: str) -> int:
        row = self._conn.execute(
            "SELECT last_ts FROM sync_state WHERE source=? AND stream=?",
            (source, stream),
        ).fetchone()
        return row[0] if row else 0

    def set_last_ts(self, source: str, stream: str, ts: int) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO sync_state(source, stream, last_ts) VALUES (?,?,?) "
                "ON CONFLICT(source, stream) DO UPDATE SET last_ts=MAX(last_ts, excluded.last_ts)",
                (source, stream, ts),
            )

    def mark_no_fit(self, key: str) -> None:
        """has_fit=2: FIT unavailable or unreadable; never requested again."""
        with self._conn:
            self._conn.execute("UPDATE activities SET has_fit=2 WHERE key=?", (key,))

    def query(self, sql: str, params: Iterable[object] = ()) -> list[tuple]:
        return self._conn.execute(sql, tuple(params)).fetchall()

    def close(self) -> None:
        self._conn.close()


def open_readonly(path: Path | str) -> sqlite3.Connection:
    """Read-only connection for the MCP/web layers (writes fail at the SQLite level)."""
    conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only = ON")
    return conn
