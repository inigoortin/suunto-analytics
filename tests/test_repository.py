import sqlite3

import pytest

from suunto_analytics.core.repository import Database, open_readonly


def test_upsert_is_idempotent_and_updates():
    db = Database()
    row = {"key": "k1", "source": "t", "start_ts": 100, "distance_m": 1000.0}
    db.upsert("activities", [row])
    db.upsert("activities", [{**row, "distance_m": 1500.0}])
    assert db.query("SELECT COUNT(*), distance_m FROM activities") == [(1, 1500.0)]


def test_unknown_table_and_column_rejected():
    db = Database()
    with pytest.raises(ValueError):
        db.upsert("activities; DROP TABLE activities", [{}])
    with pytest.raises(ValueError):
        db.upsert("activities", [{"key": "k", "x; --": 1}])


def test_composite_pk_and_cascade():
    db = Database()
    db.upsert("activities", [{"key": "a", "source": "t", "start_ts": 1}])
    db.upsert(
        "activity_laps",
        [{"activity_key": "a", "idx": 0}, {"activity_key": "a", "idx": 0}],
    )
    assert db.query("SELECT COUNT(*) FROM activity_laps") == [(1,)]
    db.query("DELETE FROM activities")
    assert db.query("SELECT COUNT(*) FROM activity_laps") == [(0,)]


def test_sync_state_never_moves_back():
    db = Database()
    db.set_last_ts("s", "sleep", 200)
    db.set_last_ts("s", "sleep", 100)
    assert db.last_ts("s", "sleep") == 200 and db.last_ts("s", "other") == 0


def test_readonly_connection_rejects_writes(tmp_path):
    path = tmp_path / "t.db"
    Database(path).upsert("recovery_samples", [{"ts": 1, "balance": 0.5}])
    ro = open_readonly(path)
    assert ro.execute("SELECT COUNT(*) FROM recovery_samples").fetchone() == (1,)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM recovery_samples")


def test_migration_adds_new_columns_to_old_db(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE activities (key TEXT PRIMARY KEY, source TEXT NOT NULL, "
        "start_ts INTEGER NOT NULL, has_fit INTEGER NOT NULL DEFAULT 0)"
    )
    old.commit()
    old.close()
    db = Database(path)
    db.upsert(
        "activities",
        [
            {
                "key": "a",
                "source": "t",
                "start_ts": 1,
                "hr_zone_bounds": "[1,2,3,4]",
                "user_max_hr": 198,
            }
        ],
    )
    assert db.query("SELECT user_max_hr FROM activities") == [(198,)]
