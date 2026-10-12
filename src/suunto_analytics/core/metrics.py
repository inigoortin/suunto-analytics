"""Pure metric functions (no I/O). Formulas documented in docs/ARCHITECTURE.md."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, datetime, timedelta

CTL_DAYS = 42
ATL_DAYS = 7


def training_load(daily_tss: dict[date, float], start: date, end: date) -> list[dict]:
    """Banister-style EWMA load per day from `start` to `end` inclusive (missing days = 0 TSS).

    ctl/atl are *end-of-day* values; tsb (form) is the previous day's ctl - atl, i.e. the freshness
    going into that day. Seed is 0, so values are low until enough history exists.
    """
    ctl = atl = 0.0
    out, day = [], start
    while day <= end:
        tss = daily_tss.get(day, 0.0)
        tsb = ctl - atl
        ctl += (tss - ctl) / CTL_DAYS
        atl += (tss - atl) / ATL_DAYS
        out.append(
            {
                "date": day.isoformat(),
                "tss": round(tss, 1),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
            }
        )
        day += timedelta(days=1)
    return out


def acwr(daily_tss: dict[date, float], end: date) -> float | None:
    """Acute:chronic workload ratio = last-7-day load / (last-28-day load / 4). None if no chronic load."""

    def total(n: int) -> float:
        return sum(daily_tss.get(end - timedelta(days=i), 0.0) for i in range(n))

    chronic = total(28) / 4
    return round(total(7) / chronic, 2) if chronic > 0 else None


def efficiency_factor(avg_speed_ms: float | None, avg_hr: float | None) -> float | None:
    """Aerobic efficiency: speed (m/min) per heartbeat-rate unit. Higher = fitter at the same effort."""
    if not avg_speed_ms or not avg_hr:
        return None
    return round(avg_speed_ms * 60 / avg_hr, 3)


def sleep_consistency(onsets_ts: Sequence[int], durations_s: Sequence[float]) -> dict:
    """Regularity of bedtime (std dev in minutes, measured from local noon so midnight doesn't wrap),
    mean duration and share of nights >= 7 h."""
    if not onsets_ts:
        return {"nights": 0}
    mins = []
    for ts in onsets_ts:
        dt = datetime.fromtimestamp(ts)
        mins.append((dt.hour * 60 + dt.minute - 12 * 60) % 1440)
    out = {
        "nights": len(mins),
        "mean_hours": round(statistics.fmean(durations_s) / 3600, 2),
        "share_ge_7h": round(
            sum(d >= 7 * 3600 for d in durations_s) / len(durations_s), 2
        ),
    }
    out["bedtime_std_min"] = (
        round(statistics.pstdev(mins), 1) if len(mins) > 1 else None
    )
    return out
