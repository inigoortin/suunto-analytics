import threading
import time

import pytest
from fastapi.testclient import TestClient

from suunto_analytics.core.repository import Database
from suunto_analytics.sources.suunto_app.runner import NeedsLogin
from suunto_analytics.web.app import HOST, create_app
from suunto_analytics.web.sync_job import SyncJob

NOW = int(time.time())


@pytest.fixture
def data_dir(tmp_path):
    db = Database(tmp_path / "suunto.db")
    db.upsert(
        "activities",
        [
            {
                "key": "r1",
                "source": "t",
                "start_ts": NOW - 3600,
                "sport": "running",
                "duration_s": 300.0,
                "distance_m": 1200.0,
                "hr_avg": 150,
                "tss": 40.0,
            },
            {
                "key": "g1",
                "source": "t",
                "start_ts": NOW - 7200,
                "sport": "strength_training",
                "duration_s": 600.0,
            },
        ],
    )
    db.upsert(
        "activity_records",
        [
            {
                "activity_key": "r1",
                "ts": NOW - 3600 + i,
                "hr": 120 + i % 30,
                "speed_ms": 4.0,
                "distance_m": 4.0 * i,
                "lat": 12.345,
                "lon": 67.891,
            }
            for i in range(300)
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
    db.set_last_ts("suunto_app", "sleep", NOW)
    db.close()
    return tmp_path


@pytest.fixture
def frontend(tmp_path):
    d = tmp_path / "fe"
    d.mkdir()
    (d / "index.html").write_text("<html>app</html>")
    return d


def client(data_dir, frontend, job=None):
    app = create_app(
        data_dir,
        frontend,
        job or SyncJob(data_dir, run=lambda _: {}),
        allowed_hosts=("testserver", "127.0.0.1", "localhost"),
    )
    return TestClient(app)


def test_summary_is_small_and_has_no_gps(data_dir, frontend):
    s = client(data_dir, frontend).get("/api/summary").json()
    assert [a["id"] for a in s["activities"]] == ["r1", "g1"]
    run = s["activities"][0]
    assert run["has_rec"] and run["has_route"] and 1 < len(run["spark"]) <= 62
    assert "rec" not in run and "route" not in run
    assert s["nights"][0]["hrv"] == 70 and s["data_until"]
    assert "12.345" not in str(s)  # no coordinates in the summary


def test_recording_on_demand_without_coordinates(data_dir, frontend):
    c = client(data_dir, frontend)
    rec = c.get("/api/activities/r1/recording").json()
    assert len(rec["hr"]) == 300 and rec["sp"] and rec["d"]
    assert "lat" not in rec and "lon" not in rec
    assert c.get("/api/activities/g1/recording").status_code == 404
    assert c.get("/api/activities/nope/recording").status_code == 404


def test_routes_only_for_gps_activities(data_dir, frontend):
    routes = client(data_dir, frontend).get("/api/routes").json()
    assert list(routes) == ["r1"] and routes["r1"][0] == [12.345, 67.891]


def test_empty_data_dir_renders_first_run_state(tmp_path, frontend):
    c = client(tmp_path / "new", frontend)
    s = c.get("/api/summary").json()
    assert (
        s["activities"] == []
        and s["nights"] == []
        and s["days"] == {}
        and s["data_until"] is None
    )
    assert c.get("/").text == "<html>app</html>"


def test_api_is_not_cached_and_binds_localhost(data_dir, frontend):
    assert (
        client(data_dir, frontend).get("/api/summary").headers["cache-control"]
        == "no-store"
    )
    assert HOST == "127.0.0.1"


def _wait(job):
    for _ in range(200):
        if not job.state()["running"]:
            return job.state()
        time.sleep(0.01)
    raise AssertionError("sync did not finish")


def test_sync_runs_once_then_enforces_gap(data_dir, frontend):
    gate, calls = threading.Event(), []

    def run(_):
        calls.append(1)
        gate.wait(2)
        return {"workouts": 1}

    job = SyncJob(data_dir, run=run, min_gap_s=900)
    c = client(data_dir, frontend, job)
    assert c.post("/api/sync").status_code == 202
    busy = c.post("/api/sync")
    assert busy.status_code == 409 and "already running" in busy.json()["reason"]
    gate.set()
    assert _wait(job)["counts"] == {"workouts": 1}
    again = c.post("/api/sync").json()
    assert not again["started"] and "try again" in again["reason"] and len(calls) == 1


def test_sync_reports_login_needed(data_dir):
    def run(_):
        raise NeedsLogin("expired")

    job = SyncJob(data_dir, run=run)
    assert job.start()[0]
    assert "suunto login" in _wait(job)["error"]
    assert job.start()[
        0
    ]  # no 15-min wait after a login problem: nothing reached Suunto
    _wait(job)


def test_rejects_foreign_hosts_and_cross_site_sync(data_dir, frontend):
    calls = []
    job = SyncJob(data_dir, run=lambda _: calls.append(1) or {})
    c = TestClient(
        create_app(data_dir, frontend, job)
    )  # default allow-list: 127.0.0.1, localhost
    assert c.get("/api/summary", headers={"host": "evil.example"}).status_code == 400
    assert (
        c.get("/api/routes", headers={"host": "evil.example:8790"}).status_code == 400
    )
    assert c.get("/api/summary", headers={"host": "127.0.0.1:8790"}).status_code == 200
    r = c.post(
        "/api/sync",
        headers={"host": "localhost:8790", "origin": "https://evil.example"},
    )
    assert r.status_code == 403 and not calls
    ok = c.post(
        "/api/sync",
        headers={"host": "localhost:8790", "origin": "http://localhost:8790"},
    )
    assert ok.status_code == 202


def test_security_headers_on_pages_and_api(data_dir, frontend):
    c = client(data_dir, frontend)
    for path in ("/", "/api/summary"):
        h = c.get(path).headers
        assert "script-src 'self';" in h["content-security-policy"]
        assert "frame-ancestors 'none'" in h["content-security-policy"]
        assert (
            h["x-content-type-options"] == "nosniff"
            and h["referrer-policy"] == "no-referrer"
        )


def test_sync_gap_survives_restart(data_dir):
    job = SyncJob(data_dir, run=lambda _: {}, min_gap_s=900)
    assert job.start()[0]
    _wait(job)
    restarted = SyncJob(data_dir, run=lambda _: {}, min_gap_s=900)
    started, reason = restarted.start()
    assert not started and "try again" in reason


def test_recording_is_capped_against_bad_timestamps(data_dir, frontend):
    db = Database(data_dir / "suunto.db")
    db.upsert(
        "activity_records", [{"activity_key": "r1", "ts": NOW + 10 * 86400, "hr": 100}]
    )
    db.close()
    rec = client(data_dir, frontend).get("/api/activities/r1/recording").json()
    assert len(rec["hr"]) == 24 * 3600


def test_recording_before_start_is_missing(data_dir, frontend):
    db = Database(data_dir / "suunto.db")
    db.upsert(
        "activities",
        [{"key": "x1", "source": "t", "start_ts": NOW, "sport": "running"}],
    )
    db.upsert("activity_records", [{"activity_key": "x1", "ts": NOW - 50, "hr": 100}])
    db.close()
    assert (
        client(data_dir, frontend).get("/api/activities/x1/recording").status_code
        == 404
    )
