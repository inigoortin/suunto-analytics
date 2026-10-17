"""MCP server (stdio). Read-only: opens the DB with mode=ro and exposes summary-style tools."""

from __future__ import annotations

import os
from contextlib import closing
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from suunto_analytics.core.repository import open_readonly
from suunto_analytics.mcp import queries as q


server = MCPServer(
    "suunto-analytics",
    instructions=(
        "Personal Suunto Race data (workouts, sleep, recovery, 24/7 steps/HR) from a local, "
        "read-only database. Start with data_overview. Prefer the summary tools; use run_sql "
        "for custom questions (SELECT only, GPS hidden)."
    ),
)

# Every tool only reads the local DB: no writes, no side effects, no network.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def _db_path() -> Path:
    return Path(os.environ.get("SUUNTO_DB", "data/suunto.db"))


def _call(fn, *args):
    """Run a query function on a fresh read-only connection that is always closed."""
    with closing(open_readonly(_db_path())) as conn:
        return fn(conn, *args)


@server.tool(annotations=READ_ONLY)
def data_overview() -> dict:
    """What data exists: row counts and date ranges per table, plus units and table names."""
    return _call(q.data_overview)


@server.tool(annotations=READ_ONLY)
def list_activities(
    limit: int = 20, days: int | None = None, sport: str | None = None
) -> list[dict]:
    """Recent workouts (newest first): key, start, sport, minutes, km, HR, TSS, training effect, VO2max."""
    return _call(q.list_activities, limit, days, sport)


@server.tool(annotations=READ_ONLY)
def get_activity(key: str) -> dict:
    """One workout's summary, per-km laps and HR zones (bpm limits + seconds); cadence in steps/min. Use a key from list_activities."""
    return _call(q.get_activity, key)


@server.tool(annotations=READ_ONLY)
def hr_zones(key: str | None = None) -> dict:
    """HR zone limits in bpm (per activity if given, else your typical limits) and their source."""
    return _call(q.hr_zones, key)


@server.tool(annotations=READ_ONLY)
def activity_series(key: str, max_points: int = 60) -> dict:
    """Downsampled time series (HR, speed km/h, altitude, power, cadence) for one workout. No GPS."""
    return _call(q.activity_series, key, max_points)


@server.tool(annotations=READ_ONLY)
def sleep_summary(days: int = 14) -> list[dict]:
    """Sleep per night: hours, stage minutes, HR avg/min, HRV, SpO2, quality (0-1)."""
    return _call(q.sleep_summary, days)


@server.tool(annotations=READ_ONLY)
def daily_summary(date: str) -> dict:
    """One local day (YYYY-MM-DD): steps, active kcal, HR range, recovery balance, workouts, sleep."""
    try:
        return _call(q.daily_summary, date)
    except ValueError:
        return {"error": "date must be YYYY-MM-DD"}


@server.tool(annotations=READ_ONLY)
def trends(metric: str, period: str = "week", n: int = 8) -> list[dict]:
    """Trend of a metric per day/week/month. Metrics: distance_km, duration_h, tss, workouts, avg_hr,
    vo2max, sleep_h, hrv_ms, sleep_hr_min, steps, recovery_balance."""
    return _call(q.trends, metric, period, n)


@server.tool(annotations=READ_ONLY)
def training_load(days: int = 42) -> dict:
    """Fitness (CTL), fatigue (ATL), form (TSB) from workout TSS, plus acute:chronic ratio. See docs/ARCHITECTURE.md."""
    return _call(q.training_load, days)


@server.tool(annotations=READ_ONLY)
def efficiency(sport: str = "running", limit: int = 20) -> list[dict]:
    """Per-workout pace, avg HR and efficiency factor (speed per HR) for a sport; track aerobic fitness."""
    return _call(q.efficiency, sport, limit)


@server.tool(annotations=READ_ONLY)
def sleep_consistency(days: int = 14) -> dict:
    """Bedtime regularity (std dev min), mean sleep hours, share of nights >= 7 h."""
    return _call(q.sleep_consistency, days)


@server.tool(annotations=READ_ONLY)
def weekly_digest() -> dict:
    """This week vs last week: workouts, km, hours, TSS, sleep, HRV, steps/day, recovery, plus current load."""
    return _call(q.weekly_digest)


@server.tool(annotations=READ_ONLY)
def run_sql(query: str, limit: int = 200) -> dict:
    """Run one read-only SELECT on the local DB (max 500 rows, 5 s). GPS columns are blocked;
    select explicit columns. Times are UTC epoch seconds; use datetime(ts,'unixepoch','localtime')."""
    return _call(q.run_sql, query, limit)


def main() -> None:
    if not _db_path().exists():
        raise SystemExit(f"database not found: {_db_path()} (run `suunto sync` first)")
    server.run("stdio")
