# Suunto Analytics

Local analytics platform for Suunto data, exposed to Claude through a read-only MCP server.
How it works (data synced, storage, metrics, security): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **Disclaimer.** Not affiliated with or endorsed by Suunto Oy. This project talks to Suunto's backend through
> [suuntool](https://github.com/tajchert/suuntool), an unofficial community tool. It is for personal and experimental
> use only and may violate Suunto's terms of service — **use it at your own risk.** You are responsible for your own
> account and data. The software is provided "as is", without warranty of any kind.

## Privacy
Everything stays on your machine. Synced data (`data/`, including the SQLite DB, raw downloads and FIT files with GPS)
is git-ignored and never uploaded by this project. Your Suunto password is never stored by this project (optionally the
macOS Keychain holds it); the session token belongs to suuntool. Don't commit `data/`, `.env` or exported files.

## Setup
1. `uv sync`
2. Install the community `suuntool` binary yourself (unofficial; may violate Suunto's ToS — use at your own risk).
   Verify its checksum, then point to it: `export SUUNTOOL_BIN=~/suuntool-bin/suuntool`
   (also auto-detected on PATH or at `~/suuntool-bin/suuntool`).
3. `uv run suunto login` — password is prompted (never echoed or stored by this project). Optionally save it
   in the macOS Keychain so an expired session is renewed silently (once per run).

## Use
- `uv run suunto sync` — incremental, polite sync into `data/suunto.db` (first run: 7 days; `--days N`, max 30).
- `uv run suunto status` — last data per stream, cooldown state, whether credentials are saved.
- Safety: 3–5 s between calls, ≤60 calls/run, any 403 (or failed login) starts a 24 h cooldown and stops all syncs.
- Tests: `uv run pytest -q`

## Dashboard app
- `uv run suunto-app` — opens http://127.0.0.1:8790 (localhost only; `--port N`, `--no-browser`).
- Reads `data/suunto.db` read-only on every page load, so it always shows the latest synced data.
- **Sync** button: runs the same polite sync as `suunto sync` (one at a time, at most once per 15 min). If the Suunto session expired it tells you to run `uv run suunto login`.
- GPS: the dashboard serves downsampled route coordinates (`/api/routes`) to its own map, on 127.0.0.1 only; the MCP server never exposes GPS.
- Plans (Plan tab) are saved in your browser only. Map tiles come from OpenStreetMap (loading them shares the map area with the tile server); everything else works offline.

## MCP server (Claude Desktop / Claude Code)
Read-only; opens `data/suunto.db` with `mode=ro`; GPS is never exposed. Tools: `data_overview`, `list_activities`,
`get_activity`, `activity_series`, `hr_zones`, `sleep_summary`, `daily_summary`, `trends`, `training_load`, `efficiency`,
`sleep_consistency`, `weekly_digest`, `run_sql` (SELECT only).

Claude Code (run once, from any directory):
```
claude mcp add suunto -e SUUNTO_DB=/path/to/suunto-analytics/data/suunto.db -- uv run --project /path/to/suunto-analytics suunto-mcp
```
Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{"mcpServers": {"suunto": {"command": "uv",
  "args": ["run", "--project", "/path/to/suunto-analytics", "suunto-mcp"],
  "env": {"SUUNTO_DB": "/path/to/suunto-analytics/data/suunto.db"}}}}
```
Refresh data with `uv run suunto sync` (the server reads the DB live; no restart needed).

## Credits
- [suuntool](https://github.com/tajchert/suuntool) by **tajchert** (MIT) — the Suunto login, workout, wellness and
  FIT export access this project relies on. This project does not bundle it; install it yourself.
- [ha-suunto](https://github.com/MichalZaniewicz/ha-suunto) by MichalZaniewicz — reference for the data model.
- Inspired by [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) and [vnglst/garmin-mcp-server](https://github.com/vnglst/garmin-mcp-server).
- Vendored: [Apache ECharts](https://echarts.apache.org) 5.5.1 (Apache-2.0), [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2-Clause).
  Map tiles © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors.

## License
MIT — see [LICENSE](LICENSE). Vendored libraries keep their own licenses (`frontend/vendor/LICENSE-*.txt`).
