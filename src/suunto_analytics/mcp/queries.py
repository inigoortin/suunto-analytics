"""Read-only query layer behind the MCP tools. Takes a read-only connection; returns plain dicts.

Privacy: GPS (lat/lon) never leaves this module; `run_sql` blocks those columns at the SQLite
authorizer level. Outputs are compact (rounded, capped) to keep token use low.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
import time
from datetime import datetime

HIDDEN_COLUMNS = {("activity_records", "lat"), ("activity_records", "lon")}
ALLOWED_OPS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}
DAY = "strftime('%Y-%m-%d', {c}, 'unixepoch', 'localtime')"

# metric -> (SQL expression over a day-grouped CTE name, table, ts column, aggregate)
TREND_METRICS = {
    "distance_km": ("SUM(distance_m)/1000.0", "activities", "start_ts"),
    "duration_h": ("SUM(duration_s)/3600.0", "activities", "start_ts"),
    "tss": ("SUM(tss)", "activities", "start_ts"),
    "workouts": ("COUNT(*)", "activities", "start_ts"),
    "avg_hr": ("AVG(hr_avg)", "activities", "start_ts"),
    "vo2max": ("AVG(vo2max_est)", "activities", "start_ts"),
    "sleep_h": ("SUM(duration_s)/3600.0", "sleep_nights", "start_ts"),
    "hrv_ms": ("AVG(hrv_avg_ms)", "sleep_nights", "start_ts"),
    "sleep_hr_min": ("AVG(hr_min_bpm)", "sleep_nights", "start_ts"),
    "steps": ("SUM(steps)", "activity_samples", "ts"),
    "recovery_balance": ("AVG(balance)", "recovery_samples", "ts"),
}
PERIODS = {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}
# Suunto default HR zones as a share of max HR; matches the limits recovered from this account's FITs.
ZONE_PCT = (0.72, 0.77, 0.82, 0.87)


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [
        {k: (round(v, 2) if isinstance(v, float) else v) for k, v in zip(cols, r)}
        for r in cur.fetchall()
    ]


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else None


def data_overview(conn: sqlite3.Connection) -> dict:
    out: dict = {}
    for table, col in (
        ("activities", "start_ts"),
        ("sleep_nights", "start_ts"),
        ("recovery_samples", "ts"),
        ("activity_samples", "ts"),
    ):
        n, lo, hi = conn.execute(
            f"SELECT COUNT(*), MIN({col}), MAX({col}) FROM {table}"
        ).fetchone()
        out[table] = {"rows": n, "from": _iso(lo), "to": _iso(hi)}
    out["notes"] = (
        "Times are local. Heart rate in bpm, distance in m, durations in s. "
        "GPS is not exposed. Tables: activities, activity_laps, activity_records "
        "(no lat/lon), sleep_nights, sleep_stages, recovery_samples, activity_samples."
    )
    return out


def list_activities(
    conn, limit: int = 20, days: int | None = None, sport: str | None = None
):
    limit = max(1, min(int(limit), 100))
    where, params = ["1=1"], []
    if days:
        where.append("start_ts >= ?")
        params.append(int(time.time()) - int(days) * 86400)
    if sport:
        where.append("sport = ?")
        params.append(sport)
    sql = (
        f"SELECT key, datetime(start_ts,'unixepoch','localtime') AS start, sport, "
        f"ROUND(duration_s/60.0,1) AS minutes, ROUND(distance_m/1000.0,2) AS km, "
        f"hr_avg, hr_max, tss, training_effect, vo2max_est, calories FROM activities "
        f"WHERE {' AND '.join(where)} ORDER BY start_ts DESC LIMIT ?"
    )
    return _rows(conn, sql, (*params, limit))


def _profile(conn) -> dict:
    try:
        return dict(conn.execute("SELECT key, value FROM user_profile").fetchall())
    except sqlite3.OperationalError:  # DB created before the table existed
        return {}


def hr_zones(conn, key: str | None = None) -> dict:
    """Heart-rate zone limits (lower bound of Z2..Z5, bpm) and where each comes from.

    Current zones (no key): custom zones from the Suunto profile, else Suunto's default zones
    (ZONE_PCT of the profile max HR), else the median of limits inferred from workouts.
    For one workout: the limits inferred from its FIT (what the watch used), else ZONE_PCT of the
    max HR stored with that workout, else the current zones.
    """
    prof = _profile(conn)
    pmax = int(prof["hr_max"]) if prof.get("hr_max") else None
    custom = (
        json.loads(prof["hr_zone_custom"]) if prof.get("hr_zone_custom") else [None] * 4
    )
    seen: list[list[int]] = [[], [], [], []]
    for (b,) in conn.execute(
        "SELECT hr_zone_bounds FROM activities WHERE hr_zone_bounds IS NOT NULL"
    ):
        for i, v in enumerate(json.loads(b)[:4]):
            if v is not None:
                seen[i].append(v)
    any_max = conn.execute("SELECT MAX(user_max_hr) FROM activities").fetchone()[0]
    current, cur_src = [], []
    for i in range(4):
        if custom[i]:
            current.append(int(custom[i]))
            cur_src.append("Suunto profile (custom)")
        elif pmax:
            current.append(round(pmax * ZONE_PCT[i]))
            cur_src.append(f"Suunto default zones, max HR {pmax}")
        elif seen[i]:
            current.append(int(statistics.median(seen[i])))
            cur_src.append("median of workouts")
        elif any_max:
            current.append(round(any_max * ZONE_PCT[i]))
            cur_src.append(f"default zones, max HR {any_max}")
        else:
            current.append(None)
            cur_src.append("unknown")
    bounds, sources = current, cur_src
    if key:
        row = conn.execute(
            "SELECT hr_zone_bounds, user_max_hr FROM activities WHERE key=?", (key,)
        ).fetchone()
        own = json.loads(row[0]) if row and row[0] else [None] * 4
        wmax = row[1] if row else None
        bounds, sources = [], []
        for i in range(4):
            if own[i] is not None:
                bounds.append(own[i])
                sources.append("recorded by the watch")
            elif wmax:
                bounds.append(round(wmax * ZONE_PCT[i]))
                sources.append(f"default zones, max HR {wmax}")
            else:
                bounds.append(current[i])
                sources.append(cur_src[i])
    return {
        "bounds_bpm": bounds,
        "sources": sources,
        "profile_max_hr": pmax,
        "profile_rest_hr": int(prof["hr_rest"]) if prof.get("hr_rest") else None,
        "zones": [
            {
                "zone": z + 1,
                "from_bpm": bounds[z - 1] if z else None,
                "to_bpm": (bounds[z] - 1) if z < 4 and bounds[z] else None,
            }
            for z in range(5)
        ],
    }


def get_activity(conn, key: str) -> dict:
    act = _rows(conn, "SELECT * FROM activities WHERE key = ?", (key,))
    if not act:
        return {"error": "activity not found"}
    laps = _rows(
        conn,
        "SELECT idx, ROUND(duration_s) AS s, ROUND(distance_m) AS m, hr_avg, hr_max, "
        "ROUND(avg_speed_ms*3.6,1) AS kmh, avg_power, avg_cadence "
        "FROM activity_laps WHERE activity_key = ? ORDER BY idx",
        (key,),
    )
    zones = hr_zones(conn, key)
    secs = json.loads(act[0]["hr_zone_s"]) if act[0].get("hr_zone_s") else [None] * 5
    for z, s_ in zip(zones["zones"], secs):
        z["seconds"] = round(s_) if s_ is not None else None
    return {
        "activity": act[0],
        "laps": laps,
        "hr_zones": zones["zones"],
        "hr_zone_sources": zones["sources"],
        "units": {"cadence": "steps/min for foot sports"},
    }


def activity_series(conn, key: str, max_points: int = 60) -> dict:
    max_points = max(10, min(int(max_points), 300))
    n = conn.execute(
        "SELECT COUNT(*) FROM activity_records WHERE activity_key=?", (key,)
    ).fetchone()[0]
    if not n:
        return {"error": "no 1 Hz records for this activity"}
    step = max(1, n // max_points)
    rows = _rows(
        conn,
        "SELECT ts, distance_m, hr, ROUND(speed_ms*3.6,1) AS kmh, altitude_m, power, "
        "cadence FROM (SELECT *, ROW_NUMBER() OVER (ORDER BY ts) AS rn "
        "FROM activity_records WHERE activity_key = ?) WHERE rn % ? = 1 ORDER BY ts",
        (key, step),
    )
    return {"points": len(rows), "every_s": step, "series": rows}


def sleep_summary(conn, days: int = 14) -> list[dict]:
    since = int(time.time()) - max(1, min(int(days), 365)) * 86400
    return _rows(
        conn,
        "SELECT datetime(start_ts,'unixepoch','localtime') AS start, is_nap, "
        "ROUND(duration_s/3600.0,2) AS hours, ROUND(deep_s/60.0) AS deep_min, "
        "ROUND(light_s/60.0) AS light_min, ROUND(rem_s/60.0) AS rem_min, "
        "ROUND(awake_s/60.0) AS awake_min, hr_avg_bpm, hr_min_bpm, hrv_avg_ms, "
        "spo2_max, quality FROM sleep_nights WHERE start_ts >= ? ORDER BY start_ts DESC",
        (since,),
    )


def daily_summary(conn, date: str) -> dict:
    datetime.strptime(date, "%Y-%m-%d")  # validates; raises ValueError on bad input
    d = DAY
    out = _rows(
        conn,
        f"SELECT SUM(steps) AS steps, ROUND(SUM(energy_kcal)) AS active_kcal, "
        f"ROUND(AVG(hr_bpm)) AS avg_hr_bpm, ROUND(MIN(hr_bpm)) AS min_hr_bpm, "
        f"ROUND(MAX(hr_bpm)) AS max_hr_bpm FROM activity_samples "
        f"WHERE {d.format(c='ts')} = ?",
        (date,),
    )[0]
    out["recovery"] = _rows(
        conn,
        f"SELECT ROUND(AVG(balance),2) AS avg_balance, "
        f"ROUND(MIN(balance),2) AS min_balance, "
        f"ROUND(MAX(balance),2) AS max_balance FROM recovery_samples "
        f"WHERE {d.format(c='ts')} = ?",
        (date,),
    )[0]
    out["workouts"] = _rows(
        conn,
        f"SELECT key, sport, ROUND(distance_m/1000.0,2) AS km, "
        f"ROUND(duration_s/60.0,1) AS minutes, hr_avg, tss FROM activities "
        f"WHERE {d.format(c='start_ts')} = ?",
        (date,),
    )
    out["sleep_ending_today"] = _rows(
        conn,
        f"SELECT ROUND(duration_s/3600.0,2) AS hours, hrv_avg_ms, "
        f"hr_min_bpm, quality FROM sleep_nights WHERE is_nap=0 AND "
        f"{d.format(c='start_ts + CAST(duration_s AS INT)')} = ?",
        (date,),
    )
    return out


def trends(conn, metric: str, period: str = "week", n: int = 8) -> list[dict]:
    if metric not in TREND_METRICS:
        return [{"error": f"unknown metric; choose from {sorted(TREND_METRICS)}"}]
    if period not in PERIODS:
        return [{"error": f"unknown period; choose from {sorted(PERIODS)}"}]
    expr, table, col = TREND_METRICS[metric]
    fmt = PERIODS[period]
    return _rows(
        conn,
        f"SELECT * FROM (SELECT strftime('{fmt}', {col}, 'unixepoch', 'localtime') AS period, "
        f"ROUND({expr}, 2) AS {metric} FROM {table} GROUP BY 1 ORDER BY 1 DESC LIMIT ?) "
        f"ORDER BY period",
        (max(1, min(int(n), 120)),),
    )


MAX_CELL_CHARS = 200
MAX_TOTAL_CHARS = 20_000
MAX_VALUE_BYTES = 1_000_000


def _cell(v):
    if isinstance(v, bytes):
        return f"<blob {len(v)} bytes>"
    if isinstance(v, str) and len(v) > MAX_CELL_CHARS:
        return v[:MAX_CELL_CHARS] + "..."
    return v


def run_sql(
    conn: sqlite3.Connection, query: str, limit: int = 200, timeout_s: float = 5.0
) -> dict:
    """SELECT-only, single statement (SQLite itself refuses more), GPS blocked at the authorizer,
    capped rows / cell size / total size / value length / time."""
    if not isinstance(query, str):
        return {"error": "query must be a string"}
    limit = max(1, min(int(limit), 500))

    def authorizer(op, a1, a2, db, src):
        if op not in ALLOWED_OPS:
            return sqlite3.SQLITE_DENY
        if op == sqlite3.SQLITE_READ and (a1, a2) in HIDDEN_COLUMNS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    deadline = time.monotonic() + timeout_s
    old_len = conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_VALUE_BYTES)
    conn.set_authorizer(authorizer)
    conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
    try:
        cur = conn.execute(query.strip().rstrip(";"))
        if cur.description is None:
            return {"error": "not a SELECT"}
        cols = [c[0] for c in cur.description]
        rows, total, truncated = [], 0, False
        for raw in cur:
            row = [_cell(v) for v in raw]
            total += sum(len(str(v)) for v in row)
            if len(rows) >= limit or total > MAX_TOTAL_CHARS:
                truncated = True
                break
            rows.append(row)
        return {"columns": cols, "rows": rows, "truncated": truncated}
    except sqlite3.Error as exc:
        hint = (
            " (lat/lon are not exposed; select explicit columns, not *)"
            if "prohibited" in str(exc)
            else ""
        )
        return {"error": f"{exc}{hint}"}
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, old_len)


# ---- derived metrics (Phase 4) -------------------------------------------------------------


def _daily_tss(conn: sqlite3.Connection) -> dict:
    from datetime import date

    return {
        date.fromisoformat(d): t
        for d, t in conn.execute(
            f"SELECT {DAY.format(c='start_ts')}, SUM(tss) FROM activities WHERE tss IS NOT NULL GROUP BY 1"
        )
    }


def training_load(conn, days: int = 42) -> dict:
    from datetime import date, timedelta
    from suunto_analytics.core.metrics import acwr, training_load as tl

    days = max(7, min(int(days), 365))
    daily, end = _daily_tss(conn), date.today()
    series = tl(daily, min(daily, default=end - timedelta(days=days)), end)[-days:]
    if not daily:
        return {
            "acwr": None,
            "latest": None,
            "series": [],
            "note": "No workouts with TSS yet.",
        }
    history = (end - min(daily)).days
    note = (
        ""
        if history >= 42
        else "Less than 6 weeks of history: CTL/TSB are understated (seeded at 0)."
    )
    if history < 28:
        note += " ACWR hidden until 28 days of history."
    return {
        "acwr": acwr(daily, end) if history >= 28 else None,
        "latest": series[-1] if series else None,
        "note": note,
        "series": series[-min(days, 60) :],
    }


def efficiency(conn, sport: str = "running", limit: int = 20) -> list[dict]:
    from suunto_analytics.core.metrics import efficiency_factor

    rows = _rows(
        conn,
        "SELECT key, datetime(start_ts,'unixepoch','localtime') AS start, "
        "ROUND(distance_m/1000.0,2) AS km, hr_avg, avg_speed_ms FROM activities "
        "WHERE sport = ? AND hr_avg > 0 AND avg_speed_ms > 0 ORDER BY start_ts DESC LIMIT ?",
        (sport, max(1, min(int(limit), 100))),
    )
    for r in rows:
        r["pace_min_km"] = round(1000 / r["avg_speed_ms"] / 60, 2)
        r["efficiency_factor"] = efficiency_factor(r.pop("avg_speed_ms"), r["hr_avg"])
    return rows


def sleep_consistency(conn, days: int = 14) -> dict:
    from suunto_analytics.core.metrics import sleep_consistency as sc

    since = int(time.time()) - max(3, min(int(days), 365)) * 86400
    data = conn.execute(
        "SELECT start_ts, duration_s FROM sleep_nights WHERE is_nap=0 AND start_ts >= ? "
        "AND duration_s IS NOT NULL",
        (since,),
    ).fetchall()
    return sc([r[0] for r in data], [r[1] for r in data])


def weekly_digest(conn, now: datetime | None = None) -> dict:
    """This ISO week (Monday 00:00 local, to now) vs the previous full week, in one compact dict.
    Sleep is attributed to the day the night starts."""
    from datetime import time as dtime, timedelta

    now = now or datetime.now()
    monday = datetime.combine(now.date() - timedelta(days=now.weekday()), dtime.min)
    bounds = {
        "this_week": (monday, monday + timedelta(days=7)),
        "last_week": (monday - timedelta(days=7), monday),
    }
    out = {}
    for label, (lo, hi) in bounds.items():
        rng = (int(lo.timestamp()), int(hi.timestamp()))
        a = _rows(
            conn,
            "SELECT COUNT(*) AS workouts, ROUND(SUM(distance_m)/1000.0,1) AS km, "
            "ROUND(SUM(duration_s)/3600.0,2) AS hours, ROUND(SUM(tss)) AS tss, "
            "ROUND(AVG(vo2max_est),1) AS vo2max FROM activities "
            "WHERE start_ts >= ? AND start_ts < ?",
            rng,
        )[0]
        sl = _rows(
            conn,
            "SELECT COUNT(*) AS nights, ROUND(AVG(duration_s)/3600.0,2) AS avg_sleep_h, "
            "ROUND(AVG(hrv_avg_ms)) AS avg_hrv, ROUND(MIN(hr_min_bpm)) AS min_hr_bpm "
            "FROM sleep_nights WHERE is_nap=0 AND start_ts >= ? AND start_ts < ?",
            rng,
        )[0]
        d = _rows(
            conn,
            f"SELECT ROUND(SUM(steps)) AS steps, COUNT(DISTINCT {DAY.format(c='ts')}) AS days "
            f"FROM activity_samples WHERE ts >= ? AND ts < ?",
            rng,
        )[0]
        r = _rows(
            conn,
            "SELECT ROUND(AVG(balance),2) AS avg_recovery FROM recovery_samples "
            "WHERE ts >= ? AND ts < ?",
            rng,
        )[0]
        out[label] = {
            "from": lo.strftime("%Y-%m-%d"),
            **a,
            **sl,
            "steps_per_day": round(d["steps"] / d["days"]) if d["steps"] else None,
            **r,
        }
    out["load"] = training_load(conn, 42)["latest"]
    return out
