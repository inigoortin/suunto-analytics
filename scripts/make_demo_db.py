"""Build a synthetic demo database: 12 weeks of an invented athlete running in Madrid's Retiro park.

Nothing here comes from a real account. Used for the README screenshot and to try the dashboard
and MCP server without a watch:

    uv run python scripts/make_demo_db.py            # writes demo-data/suunto.db
    SUUNTO_DATA_DIR=demo-data uv run suunto-app
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

from suunto_analytics.core.repository import Database

SEED = 7
WEEKS = 12
HR_MAX, HR_REST = 190, 52
ZONES = [round(HR_MAX * p) for p in (0.72, 0.77, 0.82, 0.87)]

# Retiro park outline from OpenStreetMap, pulled ~7% toward its centre so the track runs inside
# the park along the perimeter path (lat/lon degrees, ~4 km).
RETIRO_LOOP = [
    (40.41638, -3.68842), (40.41525, -3.68829), (40.41033, -3.68818), (40.40993, -3.68660),
    (40.40927, -3.68570), (40.40928, -3.68186), (40.40985, -3.67811), (40.41156, -3.67718),
    (40.41488, -3.67813), (40.41705, -3.67892), (40.41818, -3.67934), (40.42099, -3.68027),
    (40.42070, -3.68218), (40.42040, -3.68424), (40.42004, -3.68582), (40.41957, -3.68751),
    (40.41804, -3.68828), (40.41638, -3.68842),
]


def _inset(pts: list[tuple[float, float]], f: float) -> list[tuple[float, float]]:
    """Scale a loop toward its centre: a smaller loop on the park's inner paths."""
    cy, cx = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
    return [(cy + (y - cy) * f, cx + (x - cx) * f) for y, x in pts]


# (sport, weekday, start hour, minutes, kind) for a typical week; kind picks the run profile.
WEEK = [
    ("running", 1, 7.5, 40, "easy"),
    ("strength_training", 2, 19.0, 55, "gym"),
    ("running", 3, 7.5, 35, "tempo"),
    ("strength_training", 4, 19.0, 50, "gym"),
    ("flexibility_training", 5, 20.0, 25, "stretch"),
    ("running", 6, 9.5, 60, "long"),
]
PACE = {"easy": 3.05, "tempo": 3.55, "long": 2.95}  # m/s
EFFORT = {"easy": 0.70, "tempo": 0.82, "long": 0.72, "gym": 0.62, "stretch": 0.50}  # share of HR max


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    dy = (b[0] - a[0]) * 111_320
    dx = (b[1] - a[1]) * 111_320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


class Route:
    """A closed loop that returns lat/lon for any distance run along it."""

    def __init__(self, pts: list[tuple[float, float]]):
        self.pts, self.cum = pts, [0.0]
        for a, b in zip(pts, pts[1:]):
            self.cum.append(self.cum[-1] + _dist(a, b))

    def at(self, d: float) -> tuple[float, float]:
        d %= self.cum[-1]
        i = next(i for i in range(1, len(self.cum)) if self.cum[i] >= d)
        f = (d - self.cum[i - 1]) / (self.cum[i] - self.cum[i - 1])
        (a0, b0), (a1, b1) = self.pts[i - 1], self.pts[i]
        return a0 + (a1 - a0) * f, b0 + (b1 - b0) * f


class DemoAthlete:
    """Generates every table for one invented athlete, ending today."""

    def __init__(self, seed: int = SEED):
        self.rnd = random.Random(seed)
        self.end = date.today()
        self.start = self.end - timedelta(weeks=WEEKS)
        self.routes = {"perimeter": Route(RETIRO_LOOP), "inner": Route(_inset(RETIRO_LOOP, 0.6))}
        self.workouts: list[dict] = []

    def _ts(self, day: date, hour: float) -> int:
        return int(datetime.combine(day, time()).timestamp() + hour * 3600)

    def build(self, db: Database) -> None:
        db.upsert("user_profile", [
            {"key": "hr_max", "value": str(HR_MAX)}, {"key": "hr_rest", "value": str(HR_REST)},
        ])
        day = self.start
        while day <= self.end:
            self._workouts_for(db, day)
            self._night(db, day)
            day += timedelta(days=1)
        self._wellness(db)
        now = int(datetime.now().timestamp())
        for stream in ("workouts", "sleep", "recovery", "activity"):
            db.set_last_ts("demo", stream, now)

    def _workouts_for(self, db: Database, day: date) -> None:
        week_no = (day - self.start).days // 7
        for sport, wd, hour, minutes, kind in WEEK:
            if day.isoweekday() != wd or self.rnd.random() < 0.12:  # some sessions get skipped
                continue
            start = self._ts(day, hour + self.rnd.uniform(-0.3, 0.3))
            if start > datetime.now().timestamp() - 3600:
                continue
            fitness = week_no / WEEKS  # slowly improving: faster at the same effort
            mins = minutes * self.rnd.uniform(0.9, 1.1) * (1 + 0.15 * fitness * (kind == "long"))
            self._workout(db, f"demo-{day:%Y%m%d}-{wd}", sport, kind, start, int(mins * 60), fitness)

    def _workout(self, db: Database, key: str, sport: str, kind: str, start: int, dur: int, fit: float) -> None:
        run = sport == "running"
        route = self.routes["inner" if kind == "tempo" else "perimeter"]
        speed = PACE.get(kind, 0) * (1 + 0.06 * fit)
        target = HR_MAX * EFFORT[kind]
        recs, dist, hr = [], self.rnd.uniform(0, route.cum[-1]) if run else 0.0, 95.0
        offset = dist
        for s in range(dur):
            warm = min(1.0, s / 420)
            if kind == "tempo":  # 10 min warm-up, 3 x 6 min hard, easy between
                hard = 600 < s < dur - 300 and (s - 600) % 600 < 360
                want_hr, v = (HR_MAX * 0.87, speed * 1.08) if hard else (HR_MAX * 0.72, speed * 0.82)
            elif kind == "gym":  # sets: short HR peaks
                want_hr, v = target + (18 if s % 150 < 45 else -8), 0.0
            else:
                want_hr, v = target + 6 * s / dur, speed
            hr += (95 + (want_hr - 95) * warm - hr) * 0.03 + self.rnd.gauss(0, 0.8)
            v = v * (0.6 + 0.4 * warm) * self.rnd.uniform(0.96, 1.04) if run else 0.0
            dist += v
            rec = {"activity_key": key, "ts": start + s, "hr": round(hr)}
            if run:
                lat, lon = route.at(dist)
                rec.update(
                    distance_m=round(dist - offset, 1), speed_ms=round(v, 2),
                    altitude_m=round(665 + 9 * math.sin((dist % route.cum[-1]) / route.cum[-1] * 2 * math.pi), 1),
                    cadence=round(160 + 12 * (v - 2.8) + self.rnd.gauss(0, 2)),
                    lat=round(lat + self.rnd.gauss(0, 0.00002), 6), lon=round(lon + self.rnd.gauss(0, 0.00002), 6),
                )
            recs.append(rec)
        hrs = [r["hr"] for r in recs]
        zone_s = [0] * 5
        for h in hrs:
            zone_s[sum(h >= z for z in ZONES)] += 1
        hr_avg = sum(hrs) / len(hrs)
        intensity = (hr_avg - HR_REST) / (HR_MAX - HR_REST)
        meters = recs[-1].get("distance_m", 0) if run else None
        db.upsert("activities", [{
            "key": key, "source": "demo", "start_ts": start, "end_ts": start + dur, "sport": sport,
            "duration_s": dur, "elapsed_s": dur, "distance_m": meters,
            "ascent_m": round(meters / 1000 * 11) if run else None,
            "descent_m": round(meters / 1000 * 11) if run else None,
            "hr_min": min(hrs), "hr_avg": round(hr_avg), "hr_max": max(hrs),
            "avg_speed_ms": round(meters / dur, 2) if run else None,
            "max_speed_ms": round(max(r["speed_ms"] for r in recs), 2) if run else None,
            "calories": round(dur / 60 * (11 if run else 6) * intensity * 1.6),
            "tss": round(dur / 3600 * (intensity / 0.75) ** 2 * 100, 1),
            "training_effect": round(min(5.0, 1.2 + 4 * intensity * dur / 3600), 1),
            "peak_epoc": round(25 + 160 * intensity * dur / 3600),
            "vo2max_est": round(48.0 + 2.5 * fit + self.rnd.gauss(0, 0.3), 1) if run else None,
            "recovery_time_s": int(3600 * (8 + 30 * intensity * dur / 3600)),
            "avg_cadence": round(sum(r["cadence"] for r in recs) / len(recs)) if run else None,
            "hr_zone_s": json.dumps(zone_s), "has_fit": 1, "hr_zone_bounds": json.dumps(ZONES),
            "user_max_hr": HR_MAX,
        }])
        db.upsert("activity_records", recs)
        self.workouts.append({"start": start, "end": start + dur, "run": run, "tss": dur / 3600 * intensity * 100})

    def _night(self, db: Database, day: date) -> None:
        weekend = day.isoweekday() >= 5
        bed = self._ts(day, 23.2 + (0.8 if weekend else 0) + self.rnd.gauss(0, 0.35))
        dur = int(3600 * (7.4 + (0.6 if weekend else 0) + self.rnd.gauss(0, 0.45)))
        if bed + dur > datetime.now().timestamp():
            return
        stages, t = [], bed
        while t < bed + dur:  # ~90 min cycles: light, deep (front-loaded), light, REM (back-loaded)
            frac = (t - bed) / dur
            for stage, mins in (("LIGHT", 25), ("DEEP", 30 * (1 - frac)), ("LIGHT", 15), ("REM", 10 + 25 * frac)):
                s = min(int(mins * 60 * self.rnd.uniform(0.8, 1.2)), bed + dur - t)
                if s > 0:
                    stages.append({"start_ts": t, "stage": stage, "duration_s": s})
                    t += s
            if self.rnd.random() < 0.4 and t < bed + dur:
                stages.append({"start_ts": t, "stage": "AWAKE", "duration_s": 120})
                t += 120
        total = {k: sum(s["duration_s"] for s in stages if s["stage"] == k) for k in ("DEEP", "LIGHT", "REM", "AWAKE")}
        db.upsert("sleep_stages", stages)
        db.upsert("sleep_nights", [{
            "sleep_id": int(f"{day:%Y%m%d}"), "start_ts": bed, "is_nap": 0, "duration_s": dur,
            "deep_s": total["DEEP"], "light_s": total["LIGHT"], "rem_s": total["REM"], "awake_s": total["AWAKE"],
            "hr_avg_bpm": round(HR_REST + 6 + self.rnd.gauss(0, 1.5), 1),
            "hr_min_bpm": round(HR_REST + self.rnd.gauss(0, 1.5) - 2 * (day - self.start).days / (WEEKS * 7), 1),
            "hrv_avg_ms": round(58 + self.rnd.gauss(0, 7), 1), "spo2_max": round(self.rnd.uniform(0.95, 0.99), 2),
            "quality": round(min(1.0, 0.55 + 0.05 * (dur / 3600 - 6) + self.rnd.gauss(0, 0.06)), 2),
        }])

    def _wellness(self, db: Database) -> None:
        """24/7 samples every 10 min and recovery balance every 30 min."""
        t, now = self._ts(self.start, 0), int(datetime.now().timestamp())
        balance, samples, recovery = 0.8, [], []
        while t < now:
            hour = datetime.fromtimestamp(t).hour + datetime.fromtimestamp(t).minute / 60
            asleep = hour < 7 or hour >= 23.5
            w = next((w for w in self.workouts if w["start"] <= t < w["end"]), None)
            if w:
                hr, steps, kcal = 140 + self.rnd.gauss(0, 8), (1650 if w["run"] else 150), 95.0
            elif asleep:
                hr, steps, kcal = HR_REST + 4 + self.rnd.gauss(0, 2), 0, 2.0
            else:
                busy = 8 <= hour < 9 or 14 <= hour < 15 or 18 <= hour < 19
                hr = 72 + self.rnd.gauss(0, 5) + (10 if busy else 0)
                steps = max(0, int(self.rnd.gauss(350 if busy else 50, 40)))
                kcal = 3.5 + steps / 60
            samples.append({"ts": t, "hr_bpm": round(hr, 1), "steps": steps, "energy_kcal": round(kcal, 1)})
            if t % 1800 == 0:
                drain = (0.07 * w["tss"] / 60) if w else 0.012
                balance = min(1.0, balance + 0.045) if asleep else max(0.05, balance - drain)
                recovery.append({"ts": t, "balance": round(balance, 3), "stress_state": 0 if asleep else 1})
            t += 600
        db.upsert("activity_samples", samples)
        db.upsert("recovery_samples", recovery)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", nargs="?", default="demo-data", help="output folder (default: demo-data)")
    out = Path(ap.parse_args().out) / "suunto.db"
    out.unlink(missing_ok=True)
    db = Database(out)
    DemoAthlete().build(db)
    db.close()
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
