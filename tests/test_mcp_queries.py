import asyncio
import time

import pytest

from suunto_analytics.core.repository import Database, open_readonly
from suunto_analytics.mcp import queries as q

NOW = int(time.time())


@pytest.fixture
def conn(tmp_path):
    db = Database(tmp_path / "t.db")
    db.upsert(
        "activities",
        [
            {
                "key": "a1",
                "source": "t",
                "start_ts": NOW - 3600,
                "sport": "running",
                "duration_s": 1800.0,
                "distance_m": 5000.0,
                "hr_avg": 150,
                "tss": 40.0,
                "vo2max_est": 49.0,
            },
            {
                "key": "a2",
                "source": "t",
                "start_ts": NOW - 86400 * 40,
                "sport": "walking",
                "duration_s": 600.0,
                "distance_m": 1000.0,
            },
        ],
    )
    db.upsert(
        "activity_laps",
        [{"activity_key": "a1", "idx": 0, "duration_s": 300.0, "distance_m": 1000.0}],
    )
    db.upsert(
        "activity_records",
        [
            {
                "activity_key": "a1",
                "ts": NOW - 3600 + i,
                "hr": 100 + i,
                "lat": 12.345,
                "lon": 67.891,
            }
            for i in range(200)
        ],
    )
    db.upsert(
        "sleep_nights",
        [
            {
                "sleep_id": 1,
                "start_ts": NOW - 40000,
                "duration_s": 28000.0,
                "hrv_avg_ms": 70.0,
            }
        ],
    )
    db.upsert(
        "activity_samples",
        [{"ts": NOW - 600 * i, "hr_bpm": 60.0, "steps": 10} for i in range(5)],
    )
    db.upsert("recovery_samples", [{"ts": NOW - 1800, "balance": 0.6}])
    db.close()
    return open_readonly(tmp_path / "t.db")


def test_summaries(conn):
    assert q.data_overview(conn)["activities"]["rows"] == 2
    assert [a["key"] for a in q.list_activities(conn, days=7)] == ["a1"]
    assert q.list_activities(conn, sport="walking")[0]["key"] == "a2"
    g = q.get_activity(conn, "a1")
    assert (
        g["activity"]["key"] == "a1"
        and len(g["laps"]) == 1
        and q.get_activity(conn, "x")["error"]
    )
    s = q.activity_series(conn, "a1", 20)
    assert 10 <= s["points"] <= 25 and "lat" not in s["series"][0]
    assert q.sleep_summary(conn, 3)[0]["hours"] == 7.78
    d = q.daily_summary(conn, time.strftime("%Y-%m-%d"))
    assert "steps" in d and "workouts" in d
    with pytest.raises(ValueError):
        q.daily_summary(conn, "2026-13-99; DROP")


def test_trends_allowlist(conn):
    assert q.trends(conn, "distance_km", "month", 3)[-1]["distance_km"] >= 5.0
    assert "error" in q.trends(conn, "x'; DROP TABLE activities;--")[0]
    assert "error" in q.trends(conn, "tss", "year")[0]


def test_run_sql_guards(conn):
    assert q.run_sql(conn, "SELECT COUNT(*) FROM activities")["rows"] == [[2]]
    assert (
        q.run_sql(conn, "SELECT hr FROM activity_records", limit=5)["truncated"] is True
    )
    for bad in (
        "SELECT lat FROM activity_records",
        "SELECT * FROM activity_records",
        "SELECT hr FROM activity_records WHERE lon > 0",
        "DELETE FROM activities",
        "SELECT 1; SELECT 2",
        "PRAGMA table_info(activities)",
        "ATTACH 'x.db' AS x",
        "DROP TABLE activities",
        "INSERT INTO sync_state VALUES ('a','b',1)",
    ):
        assert "error" in q.run_sql(conn, bad), bad
    assert q.run_sql(conn, "SELECT COUNT(*) FROM activities")["rows"] == [
        [2]
    ]  # still intact
    slow = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM c) SELECT COUNT(*) FROM c"
    assert "error" in q.run_sql(conn, slow, timeout_s=0.3)


def test_server_registers_tools_and_calls(tmp_path, monkeypatch):
    Database(tmp_path / "s.db").upsert(
        "activities", [{"key": "z", "source": "t", "start_ts": NOW}]
    )
    monkeypatch.setenv("SUUNTO_DB", str(tmp_path / "s.db"))
    from suunto_analytics.mcp import server

    async def go():
        names = {t.name for t in (await server.server.list_tools())}
        res = await server.server.call_tool("list_activities", {"limit": 5})
        return names, res

    names, res = asyncio.run(go())
    assert {
        "data_overview",
        "list_activities",
        "get_activity",
        "activity_series",
        "sleep_summary",
        "daily_summary",
        "trends",
        "run_sql",
    } <= names
    assert "z" in str(res)


def test_every_tool_is_annotated_read_only():
    from suunto_analytics.mcp import server

    tools = asyncio.run(server.server.list_tools())
    assert len(tools) == 13
    for t in tools:
        assert t.annotations is not None, t.name
        sent = t.annotations.model_dump(by_alias=True)  # field names as clients receive them
        assert {
            k: sent[k]
            for k in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
        } == {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }, t.name


def test_run_sql_output_and_resource_caps(conn):
    big = q.run_sql(conn, "SELECT hex(zeroblob(100000)) AS x")
    assert (
        "error" in big or len(big["rows"][0][0]) <= 203
    )  # value limit or cell truncation
    blob = q.run_sql(conn, "SELECT zeroblob(10) AS b")
    assert blob["rows"] == [["<blob 10 bytes>"]]
    wide = q.run_sql(
        conn,
        "SELECT hr, hr || 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' "
        "FROM activity_records",
        limit=500,
    )
    assert wide["truncated"] or len(wide["rows"]) == 200
    assert "error" in q.run_sql(conn, "SELECT length(randomblob(500000000))")
    assert q.run_sql(conn, "SELECT ';' AS semi")["rows"] == [[";"]]
    assert "error" in q.run_sql(conn, "SELECT 1; DELETE FROM activities")
    assert "error" in q.run_sql(conn, 123)  # type: ignore[arg-type]


def test_hr_zones_activity_uses_watch_limits_then_its_max_hr(tmp_path):
    db = Database(tmp_path / "z.db")
    db.upsert(
        "activities",
        [
            {
                "key": "r1",
                "source": "t",
                "start_ts": 1,
                "hr_zone_bounds": "[143, 153, 164, null]",
                "hr_zone_s": "[10, 20, 30, 40, 0]",
                "user_max_hr": 198,
            },
            {
                "key": "r2",
                "source": "t",
                "start_ts": 2,
                "hr_zone_bounds": "[143, 152, 160, 172]",
            },
            {"key": "w", "source": "t", "start_ts": 3},
        ],
    )
    db.close()
    c = open_readonly(tmp_path / "z.db")
    z = q.hr_zones(c, "r1")
    assert z["bounds_bpm"] == [143, 153, 164, 172]
    assert z["sources"] == ["recorded by the watch"] * 3 + ["default zones, max HR 198"]
    assert q.hr_zones(c)["bounds_bpm"] == [
        143,
        152,
        162,
        172,
    ]  # no profile yet: median of workouts
    act = q.get_activity(c, "r1")
    assert act["hr_zones"][2] == {
        "zone": 3,
        "from_bpm": 153,
        "to_bpm": 163,
        "seconds": 30,
    }


def test_hr_zones_current_from_profile(tmp_path):
    db = Database(tmp_path / "p.db")
    db.upsert(
        "activities", [{"key": "a", "source": "t", "start_ts": 1, "user_max_hr": 200}]
    )
    db.close()
    assert q.hr_zones(open_readonly(tmp_path / "p.db"))["bounds_bpm"] == [
        144,
        154,
        164,
        174,
    ]
    db = Database(tmp_path / "p.db")
    db.upsert(
        "user_profile",
        [{"key": "hr_max", "value": "190"}, {"key": "hr_rest", "value": "60"}],
    )
    db.close()
    z = q.hr_zones(open_readonly(tmp_path / "p.db"))
    assert z["bounds_bpm"] == [137, 146, 156, 165] and z["profile_max_hr"] == 190
    assert z["sources"][0] == "Suunto default zones, max HR 190"
    db = Database(tmp_path / "p.db")
    db.upsert(
        "user_profile", [{"key": "hr_zone_custom", "value": "[120, 135, 150, 165]"}]
    )
    db.close()
    assert q.hr_zones(open_readonly(tmp_path / "p.db"))["bounds_bpm"] == [
        120,
        135,
        150,
        165,
    ]
