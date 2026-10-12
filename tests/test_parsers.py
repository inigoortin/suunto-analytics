from suunto_analytics.sources.suunto_app import parsers as p

SLEEP = [
    {
        "timestamp": "2026-10-04T03:30:00.000+02:00",
        "entryData": {
            "sleepId": 1,
            "duration": 28000.0,
            "deepSleepDuration": 5000.0,
            "lightSleepDuration": 15000.0,
            "remSleepDuration": 7000.0,
            "hrAvg": 1.0,
            "hrMin": 0.8,
            "avgHrv": 60.0,
            "maxSpo2": 0.97,
            "isNap": False,
            "wakeAfterSleepOnsetDuration": 60.0,
        },
    }
]


def test_sleep_units_and_time():
    (row,) = p.parse_sleep(SLEEP)
    assert (
        row["start_ts"] == 1791077400
        and row["hr_avg_bpm"] == 60.0
        and row["hr_min_bpm"] == 48.0
    )
    assert row["is_nap"] == 0 and row["awake_s"] == 60.0 and row["quality"] is None


def test_activity_samples_and_recovery_and_stages():
    (a,) = p.parse_activity_samples(
        [
            {
                "timestamp": "2026-10-04T10:40:00+02:00",
                "entryData": {"hr": 1.5, "stepCount": 12, "energyConsumption": 4184.0},
            }
        ]
    )
    assert a["hr_bpm"] == 90.0 and a["steps"] == 12 and a["energy_kcal"] == 1.0
    (r,) = p.parse_recovery(
        [
            {
                "timestamp": "2026-10-04T10:30:00+02:00",
                "entryData": {"balance": 0.5, "stressState": 2},
            }
        ]
    )
    assert r == {"ts": a["ts"] - 600, "balance": 0.5, "stress_state": 2}
    (s,) = p.parse_sleep_stages(
        [
            {
                "timestamp": "2026-10-04T03:30:00+02:00",
                "entryData": {"stage": "DEEP", "duration": 300.0},
            }
        ]
    )
    assert s["stage"] == "DEEP"


def test_workouts_json():
    rows = list(
        p.parse_workouts_json(
            {
                "items": [
                    {
                        "key": "k",
                        "startTime": 1791573123920,
                        "stopTime": 1791575000000,
                        "activityId": 1,
                        "totalTime": 2137.8,
                        "totalDistance": 5014,
                        "energyConsumption": 359,
                        "hrdata": {"workoutAvgHR": 155, "workoutMaxHR": 171},
                        "tss": {"trainingStressScore": 39.3},
                    }
                ]
            }
        )
    )
    assert rows[0]["start_ts"] == 1791573123 and rows[0]["sport"] == "running"
    assert rows[0]["hr_avg"] == 155 and rows[0]["tss"] == 39.3


def test_semicircles():
    assert p._semicircles(2**30) == 90.0 and p._semicircles(None) is None


def test_parse_fit_on_local_real_file_if_present():
    import glob
    import pytest

    files = sorted(glob.glob("data/raw/*.fit"))
    if not files:
        pytest.skip("no local FIT sample")
    d = p.parse_fit(__import__("pathlib").Path(files[0]), "k")
    assert d["activity"]["has_fit"] == 1 and d["records"]
    assert all(-90 <= r["lat"] <= 90 for r in d["records"] if r["lat"] is not None)


def test_infer_zone_bounds_recovers_limits():
    # 60 s each at 120, 140, 150, 160 and 175 bpm; zone seconds split them exactly.
    hr = [120] * 60 + [140] * 60 + [150] * 60 + [160] * 60 + [175] * 60
    assert p.infer_zone_bounds(hr, [60, 60, 60, 60, 60]) == [140, 150, 160, 175]


def test_infer_zone_bounds_unknown_when_a_side_is_too_small():
    hr = [100] * 300 + [150] * 20
    b = p.infer_zone_bounds(hr, [300, 20, 0, 0, 0])
    assert b == [None, None, None, None]
    assert p.infer_zone_bounds([], [1, 2, 3, 4, 5]) == [None] * 4
    assert p.infer_zone_bounds([1, 2], [0, 0, 0, 0, 0]) == [None] * 4


def test_running_cadence_is_steps_per_minute():
    assert p._spm(80, 0.5, True) == 161
    assert p._spm(80, None, False) == 80 and p._spm(None, 0.5, True) is None


def test_workouts_json_maps_sport_and_max_hr():
    (row,) = p.parse_workouts_json(
        {
            "items": [
                {
                    "key": "k",
                    "startTime": 0,
                    "activityId": 0,
                    "hrdata": {"userMaxHR": 198},
                }
            ]
        }
    )
    assert row["sport"] == "walking" and row["user_max_hr"] == 198


def test_parse_profile_default_and_custom_zones():
    rows = dict(
        (r["key"], r["value"])
        for r in p.parse_profile(
            {
                "hr_max": 190,
                "hr_rest": 60,
                "intensityZones": {
                    "heartRateZoneType": "max",
                    "defaultHeartRateZones": {
                        "max": {"zone2": 0, "zone3": 0, "zone4": 0, "zone5": 0}
                    },
                },
            }
        )
    )
    assert rows == {
        "hr_max": "190",
        "hr_rest": "60",
        "hr_zone_type": "max",
        "hr_zone_custom": None,
    }
    rows = dict(
        (r["key"], r["value"])
        for r in p.parse_profile(
            {
                "intensityZones": {
                    "heartRateZoneType": "max",
                    "defaultHeartRateZones": {
                        "max": {"zone2": 120, "zone3": 135, "zone4": 150, "zone5": 165}
                    },
                }
            }
        )
    )
    assert rows["hr_zone_custom"] == "[120, 135, 150, 165]"


def test_gym_and_stretching_ids_map_to_fit_sub_sports():
    assert (
        p.SPORT_BY_ID[23] == "strength_training"
        and p.SPORT_BY_ID[58] == "flexibility_training"
    )
