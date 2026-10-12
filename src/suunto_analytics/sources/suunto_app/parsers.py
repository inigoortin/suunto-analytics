"""Pure parsers: raw Suunto backend payloads -> rows for `Database.upsert`.

Unit conversions: heart rate arrives in Hz (x60 = bpm); 24/7 energy is assumed to be joules
(/4184 = kcal); timestamps become UTC epoch seconds.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path

import fitdecode

J_PER_KCAL = 4184.0


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _bpm(hz: float | None) -> float | None:
    return None if hz is None else round(hz * 60, 1)


def parse_sleep(records: Iterable[dict]) -> Iterator[dict]:
    for r in records:
        e = r["entryData"]
        yield {
            "sleep_id": int(e["sleepId"]),
            "start_ts": _ts(r["timestamp"]),
            "is_nap": int(bool(e.get("isNap"))),
            "duration_s": e.get("duration"),
            "deep_s": e.get("deepSleepDuration"),
            "light_s": e.get("lightSleepDuration"),
            "rem_s": e.get("remSleepDuration"),
            "awake_s": e.get("wakeAfterSleepOnsetDuration"),
            "hr_avg_bpm": _bpm(e.get("hrAvg")),
            "hr_min_bpm": _bpm(e.get("hrMin")),
            "hrv_avg_ms": e.get("avgHrv"),
            "spo2_max": e.get("maxSpo2"),
            "quality": e.get("quality"),
        }


def parse_sleep_stages(records: Iterable[dict]) -> Iterator[dict]:
    for r in records:
        e = r["entryData"]
        yield {
            "start_ts": _ts(r["timestamp"]),
            "stage": e["stage"],
            "duration_s": e["duration"],
        }


def parse_recovery(records: Iterable[dict]) -> Iterator[dict]:
    for r in records:
        e = r["entryData"]
        yield {
            "ts": _ts(r["timestamp"]),
            "balance": e["balance"],
            "stress_state": e.get("stressState"),
        }


def parse_activity_samples(records: Iterable[dict]) -> Iterator[dict]:
    for r in records:
        e = r["entryData"]
        energy = e.get("energyConsumption")
        yield {
            "ts": _ts(r["timestamp"]),
            "hr_bpm": _bpm(e.get("hr")),
            "steps": e.get("stepCount"),
            "energy_kcal": None if energy is None else round(energy / J_PER_KCAL, 2),
        }


# Suunto activityId -> sport (FIT naming).
SPORT_BY_ID = {
    0: "walking",
    1: "running",
    2: "cycling",
    10: "mountain_biking",
    11: "hiking",
    21: "swimming",
    22: "trail_running",
    23: "strength_training",
    51: "yoga",
    52: "indoor_cycling",
    53: "treadmill",
    58: "flexibility_training",
    73: "circuit_training",
}
# FIT stores cadence per leg for these sports; we store steps/min (x2).
FOOT_SPORTS = {"running", "walking", "hiking", "trail_running", "mountaineering"}


def infer_zone_bounds(
    hr: Iterable[int | None], zone_s: Iterable[float], min_side_s: float = 30
) -> list[int | None]:
    """Recover the four HR zone limits (lower bound of Z2..Z5, bpm) from 1 Hz HR samples.

    Suunto FIT files carry seconds per zone but not the limits. Samples sorted by HR must split
    at the same cumulative counts as the zone seconds; a limit is reported only when at least
    `min_side_s` seconds fall on each side of it.
    """
    values = sorted(v for v in hr if v is not None)
    secs = list(zone_s)[:5]
    total = sum(secs)
    if not values or total <= 0 or len(secs) < 5:
        return [None] * 4
    bounds: list[int | None] = []
    below = 0.0
    for sec in secs[:4]:
        below += sec
        if below < min_side_s or total - below < min_side_s:
            bounds.append(None)
            continue
        bounds.append(
            int(values[min(len(values) - 1, round(below / total * len(values)))])
        )
    known = [b for b in bounds if b is not None]
    return bounds if known == sorted(known) else [None] * 4


def _spm(cadence: float | None, fractional: float | None, foot: bool) -> float | None:
    if cadence is None or not foot:
        return cadence
    return round((cadence + (fractional or 0)) * 2)


def parse_workouts_json(payload: dict, source: str = "suunto_app") -> Iterator[dict]:
    """Summary rows from `workouts list` JSON (`items[]`); FIT enrichment happens separately."""
    for w in payload.get("items", []):
        hr, tss = w.get("hrdata") or {}, w.get("tss") or {}
        yield {
            "key": w["key"],
            "source": source,
            "start_ts": w["startTime"] // 1000,
            "end_ts": (w["stopTime"] // 1000) if w.get("stopTime") else None,
            "sport": SPORT_BY_ID.get(
                w.get("activityId"), f"activity_{w.get('activityId')}"
            ),
            "duration_s": w.get("totalTime"),
            "user_max_hr": hr.get("userMaxHR"),
            "distance_m": w.get("totalDistance"),
            "ascent_m": w.get("totalAscent"),
            "descent_m": w.get("totalDescent"),
            "hr_avg": hr.get("workoutAvgHR"),
            "hr_max": hr.get("workoutMaxHR"),
            "max_speed_ms": w.get("maxSpeed"),
            "calories": w.get("energyConsumption"),
            "tss": tss.get("trainingStressScore"),
            "recovery_time_s": w.get("recoveryTime"),
            "norm_power": tss.get("normalizedPower"),
        }


def parse_fit(path: Path, key: str) -> dict:
    """Return {'activity': row, 'laps': [...], 'records': [...]} from a FIT file."""
    session: dict = {}
    laps: list[dict] = []
    records: list[dict] = []
    with fitdecode.FitReader(str(path)) as reader:
        for fr in reader:
            if not isinstance(fr, fitdecode.FitDataMessage):
                continue
            if fr.name == "session":
                session = {f.name: f.value for f in fr.fields}
            elif fr.name == "lap":
                laps.append({f.name: f.value for f in fr.fields})
            elif fr.name == "record":
                records.append({f.name: f.value for f in fr.fields})
    g = session.get
    start = g("start_time")
    zones = g("time_in_hr_zone")
    foot = g("sport") in FOOT_SPORTS
    bounds = (
        infer_zone_bounds((r.get("heart_rate") for r in records), zones)
        if zones
        else None
    )
    sport = (
        g("sub_sport")
        if g("sport") == "training" and g("sub_sport") not in (None, "generic")
        else g("sport")
    )
    activity = {
        "key": key,
        "start_ts": int(start.timestamp()) if start else None,
        "sport": sport,
        "duration_s": g("total_timer_time"),
        "elapsed_s": g("total_elapsed_time"),
        "distance_m": g("total_distance"),
        "ascent_m": g("total_ascent"),
        "descent_m": g("total_descent"),
        "hr_min": g("min_heart_rate"),
        "hr_avg": g("avg_heart_rate"),
        "hr_max": g("max_heart_rate"),
        "avg_speed_ms": g("avg_speed"),
        "max_speed_ms": g("max_speed"),
        "calories": g("total_calories"),
        "tss": g("training_stress_score"),
        "training_effect": g("total_training_effect"),
        "peak_epoc": g("peak_epoc"),
        "vo2max_est": g("estimated_vo2_max"),
        "recovery_time_s": g("recovery_time"),
        "avg_power": g("avg_power"),
        "norm_power": g("normalized_power"),
        "avg_cadence": _spm(
            g("avg_running_cadence") or g("avg_cadence"),
            g("avg_fractional_cadence"),
            foot,
        ),
        "hr_zone_s": json.dumps(list(zones)) if zones else None,
        "has_fit": 1,
        "hr_zone_bounds": json.dumps(bounds)
        if bounds and any(b is not None for b in bounds)
        else None,
    }
    return {
        "activity": {k: v for k, v in activity.items() if v is not None},
        "laps": [
            {
                "activity_key": key,
                "idx": i,
                "start_ts": int(l["start_time"].timestamp()),
                "duration_s": l.get("total_timer_time"),
                "distance_m": l.get("total_distance"),
                "hr_avg": l.get("avg_heart_rate"),
                "hr_max": l.get("max_heart_rate"),
                "avg_speed_ms": l.get("avg_speed"),
                "avg_power": l.get("avg_power"),
                "avg_cadence": _spm(
                    l.get("avg_running_cadence") or l.get("avg_cadence"),
                    l.get("avg_fractional_cadence"),
                    foot,
                ),
            }
            for i, l in enumerate(laps)
            if l.get("start_time")
        ],
        "records": [
            {
                "activity_key": key,
                "ts": int(r["timestamp"].timestamp()),
                "distance_m": r.get("distance"),
                "hr": r.get("heart_rate"),
                "speed_ms": r.get("speed"),
                "altitude_m": r.get("altitude"),
                "cadence": _spm(r.get("cadence"), r.get("fractional_cadence"), foot),
                "power": r.get("power"),
                "lat": _semicircles(r.get("position_lat")),
                "lon": _semicircles(r.get("position_long")),
            }
            for r in records
            if r.get("timestamp")
        ],
    }


def parse_profile(settings: dict) -> list[dict]:
    """Key/value rows from `profile settings`: HR max/rest and the configured HR zones."""
    iz = settings.get("intensityZones") or {}
    ztype = iz.get("heartRateZoneType") or "max"
    custom = (iz.get("defaultHeartRateZones") or {}).get(ztype) or {}
    bounds = [custom.get(f"zone{i}") for i in range(2, 6)]
    rows = {
        "hr_max": settings.get("hr_max"),
        "hr_rest": settings.get("hr_rest"),
        "hr_zone_type": ztype,
        # all-zero limits mean "use Suunto's default zones"
        "hr_zone_custom": json.dumps(bounds) if any(bounds) else None,
    }
    return [{"key": k, "value": None if v is None else str(v)} for k, v in rows.items()]


def _semicircles(v: int | None) -> float | None:
    """FIT stores lat/lon as 32-bit semicircles; convert to degrees."""
    return None if v is None else round(v * (180.0 / 2**31), 6)
