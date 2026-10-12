"""Read-only builders for the dashboard: summary payload, per-activity recordings, map routes.

Used by the web app. Every function takes an open
read-only connection (`open_readonly`) and returns plain JSON-ready structures.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from suunto_analytics.mcp.queries import hr_zones

ICON = {
    "running": "run",
    "trail_running": "run",
    "treadmill": "run",
    "walking": "walk",
    "hiking": "hike",
    "strength_training": "gym",
    "circuit_training": "gym",
    "training": "gym",
    "flexibility_training": "stretch",
    "yoga": "stretch",
}
SERIES = ("hr", "speed_ms", "altitude_m", "cadence", "power", "distance_m")
SPARK_POINTS = 60
MAX_RECORDING_S = (
    24 * 3600
)  # guards against a corrupt timestamp allocating a huge series


def _r(v: float | None, nd: int = 1) -> float | None:
    return None if v is None else round(v, nd)


def _local(ts: int) -> datetime:
    return datetime.fromtimestamp(ts)


def _name(sport: str, start: datetime) -> str:
    part = (
        "Morning" if start.hour < 12 else "Afternoon" if start.hour < 18 else "Evening"
    )
    return {
        "running": f"{part} run",
        "walking": f"{part} walk",
        "strength_training": "Weight training",
        "flexibility_training": "Stretching",
    }.get(sport, sport.replace("_", " ").capitalize())


class DashboardData:
    """Builds every payload the dashboard needs from one read-only connection."""

    def __init__(self, conn: sqlite3.Connection):
        self._c = conn

    # ---------- summary (small: no 1 Hz series, no GPS) ----------
    def summary(self) -> dict:
        zones = hr_zones(self._c)
        last = self._c.execute("SELECT MAX(last_ts) FROM sync_state").fetchone()[0]
        return {
            "data_until": _local(last).strftime("%Y-%m-%d %H:%M") if last else None,
            "zones": zones["bounds_bpm"],
            "zone_sources": zones["sources"],
            "max_hr": zones["profile_max_hr"],
            "rest_hr": zones["profile_rest_hr"],
            "activities": self.activities(),
            "nights": self.nights(),
            "days": self.days(),
        }

    def activities(self) -> list[dict]:
        recorded = {
            k
            for (k,) in self._c.execute(
                "SELECT DISTINCT activity_key FROM activity_records"
            )
        }
        routed = {
            k
            for (k,) in self._c.execute(
                "SELECT DISTINCT activity_key FROM activity_records WHERE lat IS NOT NULL"
            )
        }
        out = []
        for row in self._c.execute(
            "SELECT key, start_ts, sport, duration_s, distance_m, ascent_m, hr_avg, hr_max, tss, "
            "training_effect, calories, vo2max_est, peak_epoc, recovery_time_s, hr_zone_s, "
            "hr_zone_bounds, avg_cadence, norm_power FROM activities ORDER BY start_ts DESC"
        ).fetchall():
            (
                key,
                start,
                sport,
                dur,
                dist,
                asc,
                hr,
                mx,
                tss,
                te,
                kcal,
                vo2,
                epoc,
                rec_s,
                zs,
                zb,
                cad,
                npw,
            ) = row
            dt, sport = _local(start), sport or "other"
            out.append(
                {
                    "id": key,
                    "day": dt.strftime("%Y-%m-%d"),
                    "t": dt.strftime("%H:%M"),
                    "s": ICON.get(sport, "other"),
                    "sport": sport,
                    "name": _name(sport, dt),
                    "km": round(dist / 1000, 2) if dist else None,
                    "dur": round(dur or 0),
                    "asc": _r(asc, 0),
                    "hr": hr,
                    "mx": mx,
                    "tss": round(tss or 0, 1),
                    "te": _r(te),
                    "kcal": kcal,
                    "vo2": _r(vo2),
                    "epoc": _r(epoc, 0),
                    "rec_h": round(rec_s / 3600) if rec_s else None,
                    "cad": _r(cad, 0),
                    "np": _r(npw, 0),
                    "zone_s": json.loads(zs) if zs else None,
                    "bounds": json.loads(zb) if zb else None,
                    "zb": hr_zones(self._c, key)["bounds_bpm"],
                    "has_rec": key in recorded,
                    "has_route": key in routed,
                    "spark": self._spark(key, start, dur) if key in recorded else None,
                }
            )
        return out

    def _spark(self, key: str, start: int, dur: float | None) -> list[int]:
        """~60-point average-HR line for the activity list (tiny, so the list needs no recordings)."""
        span = max(1, int(dur or 1))
        rows = self._c.execute(
            "SELECT (ts - ?) * ? / ? AS b, AVG(hr) FROM activity_records WHERE activity_key=? AND hr > 0 "
            "GROUP BY b ORDER BY b",
            (start, SPARK_POINTS, span, key),
        ).fetchall()
        return [round(h) for _, h in rows if h is not None]

    def nights(self) -> list[dict]:
        out = []
        for (
            start,
            dur,
            deep,
            light,
            rem,
            awake,
            hr_avg,
            hr_min,
            hrv,
            spo2,
            q,
        ) in self._c.execute(
            "SELECT start_ts, duration_s, deep_s, light_s, rem_s, awake_s, hr_avg_bpm, hr_min_bpm, "
            "hrv_avg_ms, spo2_max, quality FROM sleep_nights WHERE is_nap=0 ORDER BY start_ts"
        ):
            st = _local(start)
            bed = st.hour * 60 + st.minute - (1440 if st.hour >= 18 else 0)
            wake = _local(start + int(dur or 0))
            out.append(
                {
                    "date": wake.strftime("%Y-%m-%d"),
                    "bed": bed,
                    "h": _r((dur or 0) / 3600, 2),
                    "deep": _r((deep or 0) / 60, 0),
                    "light": _r((light or 0) / 60, 0),
                    "rem": _r((rem or 0) / 60, 0),
                    "awake": _r((awake or 0) / 60, 0),
                    "hr_avg": _r(hr_avg, 0),
                    "hr_min": _r(hr_min, 0),
                    "hrv": _r(hrv, 0),
                    "spo2": _r(spo2, 2),
                    "q": _r(q, 2),
                }
            )
        return out

    def days(self) -> dict:
        """Per local day: steps, active kcal, 24/7 HR min/avg, recovery balance (max, last)."""
        days: dict[str, dict] = {}
        for ts, hr, steps, kcal in self._c.execute(
            "SELECT ts, hr_bpm, steps, energy_kcal FROM activity_samples"
        ):
            d = days.setdefault(
                _local(ts).strftime("%Y-%m-%d"), {"steps": 0, "kcal": 0.0, "hr": []}
            )
            d["steps"] += steps or 0
            d["kcal"] += kcal or 0
            if hr:
                d["hr"].append(hr)
        rec: dict[str, list] = {}
        for ts, bal in self._c.execute(
            "SELECT ts, balance FROM recovery_samples ORDER BY ts"
        ):
            rec.setdefault(_local(ts).strftime("%Y-%m-%d"), []).append(bal)
        out = {}
        for day in sorted(set(days) | set(rec)):
            d, r = (
                days.get(day, {"steps": None, "kcal": None, "hr": []}),
                rec.get(day, []),
            )
            out[day] = {
                "steps": d["steps"],
                "kcal": _r(d["kcal"], 0) if d["kcal"] is not None else None,
                "hr_min": _r(min(d["hr"]), 0) if d["hr"] else None,
                "hr_avg": _r(sum(d["hr"]) / len(d["hr"]), 0) if d["hr"] else None,
                "rec_max": _r(max(r) * 100, 0) if r else None,
                "rec_last": _r(r[-1] * 100, 0) if r else None,
            }
        return out

    # ---------- heavy, on demand ----------
    def recording(self, key: str) -> dict | None:
        """1 Hz series for one activity (no GPS), indexed by second from the start."""
        start = self._c.execute(
            "SELECT start_ts FROM activities WHERE key=?", (key,)
        ).fetchone()
        rows = self._c.execute(
            f"SELECT ts, {', '.join(SERIES)} FROM activity_records WHERE activity_key=? "
            "ORDER BY ts",
            (key,),
        ).fetchall()
        if not start or not rows:
            return None
        start, n = start[0], min(rows[-1][0] - start[0] + 1, MAX_RECORDING_S)
        if (
            n <= 0
        ):  # records all before the activity start: inconsistent, treat as missing
            return None
        cols = {c: [None] * n for c in SERIES}
        for ts, *vals in rows:
            i = ts - start
            if 0 <= i < n:
                for c, v in zip(SERIES, vals):
                    cols[c][i] = round(v, 2) if isinstance(v, float) else v
        for c in SERIES:  # forward-fill short gaps so per-bin averages stay defined
            last = next((v for v in cols[c] if v is not None), None)
            for i, v in enumerate(cols[c]):
                cols[c][i] = last = v if v is not None else last
        has = {c: any(v not in (None, 0) for v in cols[c]) for c in SERIES}
        return {
            "hr": cols["hr"],
            "sp": cols["speed_ms"] if has["speed_ms"] else None,
            "al": cols["altitude_m"],
            "cd": cols["cadence"] if has["cadence"] else None,
            "pw": cols["power"] if has["power"] else None,
            "d": cols["distance_m"] if has["distance_m"] else None,
        }

    def routes(self, limit: int = 50, every: int = 5) -> dict[str, list]:
        """Downsampled lat/lon of the latest GPS activities, for the local map only."""
        keys = [
            k
            for (k,) in self._c.execute(
                "SELECT a.key FROM activities a WHERE EXISTS (SELECT 1 FROM activity_records r "
                "WHERE r.activity_key=a.key AND r.lat IS NOT NULL) ORDER BY a.start_ts DESC LIMIT ?",
                (limit,),
            )
        ]
        out = {}
        for key in keys:
            pts = self._c.execute(
                "SELECT lat, lon FROM activity_records WHERE activity_key=? AND lat IS NOT NULL "
                "ORDER BY ts",
                (key,),
            ).fetchall()
            out[key] = [[round(a, 5), round(b, 5)] for a, b in pts[::every]]
        return out
