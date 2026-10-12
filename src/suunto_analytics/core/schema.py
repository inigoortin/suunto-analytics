"""SQLite schema. Idempotent (`CREATE ... IF NOT EXISTS`). All times are UTC epoch seconds."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS activities (
    key TEXT PRIMARY KEY,            -- Suunto workout key
    source TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER,
    sport TEXT,                      -- FIT sport name if known, else 'activity_<id>'
    duration_s REAL,
    elapsed_s REAL,
    distance_m REAL,
    ascent_m REAL,
    descent_m REAL,
    hr_min INTEGER, hr_avg INTEGER, hr_max INTEGER,
    avg_speed_ms REAL, max_speed_ms REAL,
    calories INTEGER,
    tss REAL, training_effect REAL, peak_epoc REAL,
    vo2max_est REAL,
    recovery_time_s INTEGER,
    avg_power REAL, norm_power REAL, avg_cadence REAL,
    hr_zone_s TEXT,                  -- JSON list of seconds per zone
    has_fit INTEGER NOT NULL DEFAULT 0,
    hr_zone_bounds TEXT,             -- JSON [Z2, Z3, Z4, Z5] lower bounds in bpm (inferred; null = unknown)
    user_max_hr INTEGER              -- max HR configured in the Suunto profile
);
CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_ts);

CREATE TABLE IF NOT EXISTS activity_laps (
    activity_key TEXT NOT NULL REFERENCES activities(key) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_ts INTEGER, duration_s REAL, distance_m REAL,
    hr_avg INTEGER, hr_max INTEGER, avg_speed_ms REAL, avg_power REAL, avg_cadence REAL,
    PRIMARY KEY (activity_key, idx)
);

CREATE TABLE IF NOT EXISTS activity_records (   -- 1 Hz samples; lat/lon are sensitive
    activity_key TEXT NOT NULL REFERENCES activities(key) ON DELETE CASCADE,
    ts INTEGER NOT NULL,
    distance_m REAL, hr INTEGER, speed_ms REAL, altitude_m REAL,
    cadence INTEGER, power INTEGER, lat REAL, lon REAL,   -- cadence: steps/min for foot sports
    PRIMARY KEY (activity_key, ts)
);

CREATE TABLE IF NOT EXISTS sleep_nights (
    sleep_id INTEGER PRIMARY KEY,
    start_ts INTEGER NOT NULL,
    is_nap INTEGER NOT NULL DEFAULT 0,
    duration_s REAL, deep_s REAL, light_s REAL, rem_s REAL, awake_s REAL,
    hr_avg_bpm REAL, hr_min_bpm REAL, hrv_avg_ms REAL, spo2_max REAL, quality REAL
);
CREATE INDEX IF NOT EXISTS idx_sleep_start ON sleep_nights(start_ts);

CREATE TABLE IF NOT EXISTS sleep_stages (
    start_ts INTEGER PRIMARY KEY,
    stage TEXT NOT NULL,             -- LIGHT | DEEP | REM | AWAKE
    duration_s REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_samples (
    ts INTEGER PRIMARY KEY,
    balance REAL NOT NULL,           -- 0..1
    stress_state INTEGER
);

CREATE TABLE IF NOT EXISTS activity_samples (   -- 24/7, 10-minute buckets
    ts INTEGER PRIMARY KEY,
    hr_bpm REAL, steps INTEGER, energy_kcal REAL
);

CREATE TABLE IF NOT EXISTS user_profile (   -- selected Suunto profile settings (HR max/rest, zones)
    key TEXT PRIMARY KEY, value TEXT
);

CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT NOT NULL, stream TEXT NOT NULL, last_ts INTEGER NOT NULL,
    PRIMARY KEY (source, stream)
);
"""

# Columns added after the first release: (table, column, type). Applied by Database on open.
ADDED_COLUMNS = (
    ("activities", "hr_zone_bounds", "TEXT"),
    ("activities", "user_max_hr", "INTEGER"),
)
