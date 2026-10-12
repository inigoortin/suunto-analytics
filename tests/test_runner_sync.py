import json
import subprocess
from pathlib import Path

import pytest

from suunto_analytics.core.credentials import CredentialStore
from suunto_analytics.core.http_client import CircuitOpen, Cooldown, CooldownActive
from suunto_analytics.core.repository import Database
from suunto_analytics.sources.suunto_app.runner import NeedsLogin, SuuntoolRunner
from suunto_analytics.sources.suunto_app.sync import SyncService


class FakeKeyring:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p

    def delete_password(self, s, u):
        self.d.pop((s, u), None)


def runner(tmp_path, script, creds=None, **kw):
    calls = []

    def fake_run(argv, input=None, **_):
        calls.append((argv[1:], input))
        rc, write = script(argv[1:], len(calls))
        if write:
            Path(argv[argv.index("-o") + 1]).write_text(write)
        return subprocess.CompletedProcess(argv, rc, "", "")

    r = SuuntoolRunner(
        Path("suuntool"),
        Cooldown(tmp_path / "cd.json"),
        creds or CredentialStore(FakeKeyring()),
        run=fake_run,
        sleep=lambda s: None,
        jitter=0.0,
        **kw,
    )
    return r, calls


def test_expired_session_relogs_in_once_with_keychain(tmp_path):
    kr = CredentialStore(FakeKeyring())
    kr.save("a@b.c", "pw")
    state = {"n": 0}

    def script(args, n):
        if args[0] == "login":
            return 0, None
        state["n"] += 1
        return (4, None) if state["n"] == 1 else (0, None)

    r, calls = runner(tmp_path, script, kr)
    r.call(["doctor"])
    assert [c[0][0] for c in calls] == ["doctor", "login", "doctor"]
    assert calls[1][1] == "pw" and "--password" not in calls[1][0]  # stdin only


def test_expired_without_credentials_needs_login(tmp_path):
    r, _ = runner(tmp_path, lambda a, n: (4, None))
    with pytest.raises(NeedsLogin):
        r.call(["doctor"])


def test_forbidden_trips_breaker_and_cooldown(tmp_path):
    r, calls = runner(tmp_path, lambda a, n: (7, None))
    with pytest.raises(CircuitOpen):
        r.call(["doctor"])
    with pytest.raises(CooldownActive):
        r.call(["doctor"])
    assert len(calls) == 1


def test_sync_idempotent_and_incremental(tmp_path):
    sleep = json.dumps(
        {
            "timestamp": "2026-10-04T03:30:00+02:00",
            "entryData": {"sleepId": 1, "duration": 100.0, "hrAvg": 1.0},
        }
    )
    wk = json.dumps(
        {"items": [{"key": "k1", "startTime": 1791573123920, "activityId": 1}]}
    )

    def script(args, n):
        if args[0] == "wellness" and args[1] == "sleep":
            return 0, sleep
        if args[0] == "wellness":
            return 0, ""
        if args[:2] == ["workouts", "list"]:
            return 0, wk
        if args[:2] == ["profile", "settings"]:
            return 0, json.dumps({"hr_max": 190, "hr_rest": 60})
        return 6, None  # fit: not found -> skipped

    r, calls = runner(tmp_path, script, max_calls=100)
    db = Database()
    svc = SyncService(r, db, tmp_path / "raw", now=1791600000, default_days=3)
    assert svc.sync()["sleep"] == 1 and svc.sync()["sleep"] == 1
    assert db.query("SELECT COUNT(*) FROM sleep_nights") == [(1,)]
    assert db.last_ts("suunto_app", "sleep") == 1791077400
    since_args = [
        c[0][c[0].index("--since") + 1]
        for c in calls
        if c[0][:2] == ["wellness", "sleep"]
    ]
    assert (
        since_args[0] != since_args[1]
    )  # 2nd run is incremental (from last_ts - 1 day)
    assert dict(db.query("SELECT key, value FROM user_profile"))["hr_max"] == "190"


def test_persistent_failure_starts_short_cooldown(tmp_path):
    from suunto_analytics.sources.suunto_app.runner import SuuntoolError

    r, calls = runner(tmp_path, lambda a, n: (5, None))
    with pytest.raises(SuuntoolError):
        r.call(["doctor"])
    assert len(calls) == 3  # bounded retries
    with pytest.raises(CooldownActive):
        r.call(["doctor"])


def test_failed_login_starts_cooldown_and_never_retries(tmp_path):
    from suunto_analytics.sources.suunto_app.runner import SuuntoolError

    r, calls = runner(tmp_path, lambda a, n: (4, None))
    with pytest.raises(SuuntoolError):
        r.login("a@b.c", "pw")
    assert len(calls) == 1
    with pytest.raises(CooldownActive):
        r.login("a@b.c", "pw")


def test_timeout_is_wrapped_and_call_cap(tmp_path):
    from suunto_analytics.core.http_client import RequestCapReached
    from suunto_analytics.sources.suunto_app.runner import SuuntoolError

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)

    r = SuuntoolRunner(
        Path("s"),
        Cooldown(tmp_path / "c.json"),
        CredentialStore(FakeKeyring()),
        run=boom,
        sleep=lambda s: None,
        jitter=0.0,
        max_calls=1,
    )
    with pytest.raises(SuuntoolError):
        r.call(["doctor"])
    with pytest.raises(RequestCapReached):
        r.call(["doctor"])


def test_missing_and_corrupt_fit_are_marked_and_not_retried(tmp_path):
    wk = json.dumps(
        {
            "items": [
                {"key": "k1", "startTime": 1791573123920, "activityId": 1},
                {"key": "k2", "startTime": 1791573123921, "activityId": 1},
            ]
        }
    )

    def script(args, n):
        if args[:2] == ["workouts", "list"]:
            return 0, wk
        if args[:2] == ["workouts", "fit"]:
            return (6, None) if args[2] == "k1" else (0, "not a fit file")
        if args[:2] == ["profile", "settings"]:
            return 0, "{}"
        return 0, ""

    r, calls = runner(tmp_path, script, max_calls=200)
    db = Database()
    svc = SyncService(r, db, tmp_path / "raw", now=1791600000)
    svc.sync()
    assert db.query("SELECT key, has_fit FROM activities ORDER BY key") == [
        ("k1", 2),
        ("k2", 2),
    ]
    n = len(calls)
    svc.sync()
    assert not [
        c for c in calls[n:] if c[0][:2] == ["workouts", "fit"]
    ]  # never re-requested


def test_credentials_forget():
    store = CredentialStore(FakeKeyring())
    store.save("a@b.c", "pw")
    assert store.get() == ("a@b.c", "pw")
    store.forget()
    assert store.get() is None and store.email() is None


def test_reparse_cached_uses_no_network(tmp_path):
    import json as _json
    from suunto_analytics.core.repository import Database as _DB
    from suunto_analytics.sources.suunto_app.sync import reparse_cached

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "workouts.json").write_text(
        _json.dumps(
            {
                "items": [
                    {
                        "key": "k1",
                        "startTime": 1000,
                        "activityId": 1,
                        "hrdata": {"userMaxHR": 198},
                    }
                ]
            }
        )
    )
    (raw / "workout_k1.fit").write_bytes(b"not a fit file")
    db = _DB()
    counts = reparse_cached(db, raw)
    assert counts == {"workouts": 1, "fit": 0, "fit_failed": 1, "profile": 0}
    assert db.query("SELECT sport, user_max_hr FROM activities") == [("running", 198)]
