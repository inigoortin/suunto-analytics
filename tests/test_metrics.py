from datetime import date, datetime, timedelta

import pytest

from suunto_analytics.core import metrics as m
from suunto_analytics.core.repository import Database, open_readonly
from suunto_analytics.mcp import queries as q


def test_training_load_known_values():
    d0 = date(2026, 1, 1)
    out = m.training_load({d0: 100.0}, d0, d0 + timedelta(days=1))
    assert out[0]["ctl"] == pytest.approx(2.4, abs=0.05) and out[0][
        "atl"
    ] == pytest.approx(14.3, abs=0.05)
    assert out[0]["tsb"] == 0.0
    assert out[1]["tsb"] == pytest.approx(
        out[0]["ctl"] - out[0]["atl"], abs=0.1
    )  # form = prev day


def test_constant_load_converges_and_rest_decays():
    d0 = date(2026, 1, 1)
    daily = {d0 + timedelta(days=i): 100.0 for i in range(300)}
    out = m.training_load(daily, d0, d0 + timedelta(days=330))
    assert out[299]["ctl"] > 99 and out[299]["atl"] == pytest.approx(100, abs=0.1)
    assert (
        out[-1]["atl"] < 1 and out[-1]["ctl"] < out[299]["ctl"]
    )  # decays during rest, ATL faster


def test_acwr():
    end = date(2026, 3, 1)
    steady = {end - timedelta(days=i): 50.0 for i in range(28)}
    assert m.acwr(steady, end) == 1.0
    assert m.acwr({}, end) is None
    spike = {**steady, **{end - timedelta(days=i): 150.0 for i in range(7)}}
    assert m.acwr(spike, end) > 1.5


def test_efficiency_factor():
    assert m.efficiency_factor(3.0, 150) == 1.2
    assert (
        m.efficiency_factor(None, 150) is None and m.efficiency_factor(3.0, 0) is None
    )


def test_sleep_consistency_handles_midnight_wrap():
    def ts(day, hour, minute=0):
        return int(datetime(2026, 3, day, hour, minute).timestamp())

    onsets = [
        ts(1, 23, 30),
        ts(3, 0, 30),
        ts(4, 23, 30),
    ]  # 23:30, 00:30, 23:30 -> small spread
    r = m.sleep_consistency(onsets, [8 * 3600, 6 * 3600, 7 * 3600])
    assert r["nights"] == 3 and r["bedtime_std_min"] < 60 and r["share_ge_7h"] == 0.67
    assert m.sleep_consistency([], []) == {"nights": 0}
    assert m.sleep_consistency([ts(1, 23)], [3600])["bedtime_std_min"] is None


def test_query_wrappers_on_synthetic_db(tmp_path):
    import time

    now = int(time.time())
    db = Database(tmp_path / "t.db")
    db.upsert(
        "activities",
        [
            {
                "key": "r1",
                "source": "t",
                "start_ts": now - 3600,
                "sport": "running",
                "duration_s": 1800.0,
                "distance_m": 5000.0,
                "hr_avg": 150,
                "avg_speed_ms": 3.0,
                "tss": 40.0,
            },
            {
                "key": "r0",
                "source": "t",
                "start_ts": now - 86400 * 50,
                "sport": "running",
                "distance_m": 4000.0,
                "hr_avg": 150,
                "avg_speed_ms": 2.9,
                "tss": 30.0,
            },
        ],
    )
    db.close()
    c = open_readonly(tmp_path / "t.db")
    tl = q.training_load(c, 14)
    assert tl["latest"]["ctl"] > 0 and tl["acwr"] is not None and tl["note"] == ""
    e = q.efficiency(c, "running", 5)
    assert e[0]["efficiency_factor"] == 1.2 and e[0]["pace_min_km"] == 5.56
    assert q.sleep_consistency(c)["nights"] == 0
    assert q.weekly_digest(c)["this_week"]["workouts"] >= 0


def test_weekly_digest_week_boundaries_and_new_year(tmp_path):
    def ts(y, mth, d, h=12):
        return int(datetime(y, mth, d, h).timestamp())

    db = Database(tmp_path / "w.db")
    # "now" = Thu 2026-01-01; this week starts Mon 2025-12-29, last week Mon 2025-12-22
    db.upsert(
        "activities",
        [
            {
                "key": "a",
                "source": "t",
                "start_ts": ts(2025, 12, 29),
                "distance_m": 1000.0,
                "tss": 10.0,
            },
            {
                "key": "b",
                "source": "t",
                "start_ts": ts(2026, 1, 1, 9),
                "distance_m": 2000.0,
                "tss": 20.0,
            },
            {
                "key": "c",
                "source": "t",
                "start_ts": ts(2025, 12, 28, 23),
                "distance_m": 5000.0,
                "tss": 50.0,
            },
            {
                "key": "d",
                "source": "t",
                "start_ts": ts(2025, 12, 22),
                "distance_m": 7000.0,
                "tss": 70.0,
            },
            {
                "key": "e",
                "source": "t",
                "start_ts": ts(2025, 12, 21, 23),
                "distance_m": 9000.0,
            },
        ],
    )
    db.upsert(
        "sleep_nights",
        [
            {"sleep_id": 1, "start_ts": ts(2025, 12, 30, 23), "duration_s": 28800.0},
            {
                "sleep_id": 2,
                "start_ts": ts(2025, 12, 30, 14),
                "duration_s": 1800.0,
                "is_nap": 1,
            },
        ],
    )
    db.close()
    c = open_readonly(tmp_path / "w.db")
    d = q.weekly_digest(c, now=datetime(2026, 1, 1, 18))
    assert (
        d["this_week"]["workouts"] == 2 and d["this_week"]["km"] == 3.0
    )  # spans New Year, one week
    assert d["last_week"]["workouts"] == 2 and d["last_week"]["tss"] == 120.0
    assert d["this_week"]["nights"] == 1 and d["this_week"]["avg_sleep_h"] == 8.0
    assert (
        d["this_week"]["from"] == "2025-12-29"
        and d["last_week"]["from"] == "2025-12-22"
    )


def test_empty_db_load_is_none(tmp_path):
    Database(tmp_path / "e.db").close()
    c = open_readonly(tmp_path / "e.db")
    assert q.training_load(c)["latest"] is None
    assert q.weekly_digest(c)["load"] is None
    assert q.efficiency(c) == [] and q.sleep_consistency(c) == {"nights": 0}
