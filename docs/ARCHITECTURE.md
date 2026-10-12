# How it works

```
suuntool (your Suunto account)
   │  serial, throttled calls; raw responses cached in data/raw/
   ▼
parsers ──► SQLite (data/suunto.db) ──► metrics ──┬──► MCP server (read-only)  → Claude Desktop / Claude Code
                                                  └──► dashboard (FastAPI, 127.0.0.1) → your browser
```

All data stays on your machine. The only network traffic is the sync itself (through suuntool) and, on the
dashboard map, OpenStreetMap tiles.

## Code layout
| Path | Role |
|---|---|
| `src/suunto_analytics/sources/suunto_app/` | `runner.py` wraps the suuntool binary (session reuse, throttle, call cap, cooldown); `parsers.py` turns JSON, NDJSON and FIT into rows; `sync.py` runs the incremental sync |
| `src/suunto_analytics/core/` | SQLite schema and repository, metric functions, credential storage (OS keychain), `PoliteClient` for direct HTTP |
| `src/suunto_analytics/mcp/` | MCP server and its read-only queries |
| `src/suunto_analytics/web/` | Dashboard backend: API payloads (`data.py`), Sync button job (`sync_job.py`), FastAPI app (`app.py`) |
| `frontend/` | Plain JavaScript, no build step: `boot.js` → `core.js` → `views.js` → `dash.js`; ECharts and Leaflet vendored |
| `tests/` | pytest suite on synthetic data |

## Data synced
| Stream | Granularity | Main fields |
|---|---|---|
| Workouts | per workout | sport, start/stop, duration, distance, ascent/descent, HR avg/max, TSS, training effect, EPOC, VO2max estimate, recovery time, time in HR zones |
| Workout recording (FIT) | 1 Hz, plus laps | HR, speed, distance, altitude, cadence, power, temperature, GPS |
| Sleep | per night (and naps) | duration, deep/light/REM, HR avg/min, HRV, SpO2, quality |
| Sleep stages | per segment | stage (light/deep/REM/awake), duration |
| Recovery | ~30 min | balance (0–1), stress state |
| 24/7 activity | 10 min | HR, steps, energy |
| Profile | per sync | max HR, resting HR, zone settings |

Unit conversions done by the parsers: wellness HR comes in Hz (×60 → bpm), timestamps are stored as UTC epoch,
foot-sport FIT cadence is per leg and is stored as steps/min.

## Storage
SQLite tables: `activities`, `activity_laps`, `activity_records` (1 Hz samples, including GPS), `sleep_nights`,
`sleep_stages`, `recovery_samples`, `activity_samples` (24/7), `user_profile`, `sync_state`. The schema is created
with `CREATE TABLE IF NOT EXISTS` and migrated automatically. Raw downloads are kept in `data/raw/` (files 0600,
folder 0700) so that `suunto reparse` can rebuild the tables after a parser change without contacting Suunto.

## Metrics
- **TSS** per workout: taken from the watch (FIT `training_stress_score`), not recomputed.
- **Fitness / fatigue (CTL / ATL)**: daily exponentially weighted average of TSS, `x += (tss − x) / N`, N = 42 and 7;
  days without workouts count as 0. **Form (TSB)** = previous day's CTL − ATL. Needs ~6 weeks of history to be meaningful.
- **ACWR**: last-7-day TSS ÷ (last-28-day TSS ÷ 4). Roughly 0.8–1.3 is steady, above 1.5 is a spike.
- **Efficiency factor**: average speed (m/min) ÷ average HR; compare only similar efforts and terrain.
- **Sleep consistency**: standard deviation of bedtime, mean sleep hours, share of nights ≥ 7 h (naps excluded).
- **Resting HR**: nightly minimum HR from sleep. **VO2max**: the watch's per-run estimate.
- **Weekly digest**: Monday 00:00 to now vs the previous full Monday–Sunday week.
- **HR zones**: FIT files store time per zone but not the limits, so the limits are inferred from the 1 Hz HR samples
  (samples sorted and split at the same cumulative counts as the zone times). Fallback: 72/77/82/87 % of max HR,
  the Suunto default zones.

## Being polite to Suunto's backend
- One request at a time, 3–5 s apart, at most 60 calls per run; the session is reused instead of logging in again.
- Incremental: only data newer than what is stored is fetched; the first sync covers 7 days (max 30 per run).
- Any 401/403/429 or a failed login stops the run and starts a 24 h cooldown shared by the CLI and the dashboard.
- The dashboard's Sync button runs at most once every 15 minutes; the MCP server and the dashboard never call Suunto
  on their own.

## Security and privacy
- **Credentials**: the password is prompted, never echoed, logged or written by this project; it is saved only in the
  OS keychain if you opt in. The session token is managed by suuntool.
- **MCP server**: opens the database with `mode=ro`. `run_sql` accepts a single `SELECT` only (no writes, `PRAGMA`
  or `ATTACH`), caps rows and output size, and cannot read GPS columns.
- **Dashboard**: binds to 127.0.0.1 only, accepts only `localhost`/`127.0.0.1` hosts (blocks DNS rebinding),
  checks the Origin on `POST /api/sync`, and sends a strict Content-Security-Policy, `nosniff` and `no-referrer`.
  Text from the database is HTML-escaped. GPS is served only to the dashboard's own map.
- **Repository**: `data/`, `.env`, `*.fit`, `*.db` and token/secret files are git-ignored; tests use synthetic data.
