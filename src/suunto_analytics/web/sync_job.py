"""Runs the polite sync from the dashboard's Sync button: one run at a time, never on a timer."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from suunto_analytics.core.credentials import CredentialStore
from suunto_analytics.core.http_client import Cooldown, PoliteClientError
from suunto_analytics.core.repository import Database
from suunto_analytics.sources.suunto_app.runner import (
    NeedsLogin,
    SuuntoolRunner,
    find_suuntool,
)
from suunto_analytics.sources.suunto_app.sync import SyncService

MIN_GAP_S = 15 * 60  # the button cannot start a sync more often than this


def _default_sync(data_dir: Path) -> dict[str, int]:
    binary = find_suuntool()
    if not binary:
        raise RuntimeError("suuntool binary not found; set SUUNTOOL_BIN (see README).")
    runner = SuuntoolRunner(
        binary, Cooldown(data_dir / "cooldown.json"), CredentialStore()
    )
    db = Database(data_dir / "suunto.db")
    try:
        return SyncService(runner, db, data_dir / "raw").sync()
    finally:
        db.close()


class SyncJob:
    """Background sync with a lock and a minimum gap. State is safe to read from request handlers."""

    def __init__(
        self,
        data_dir: Path,
        *,
        run: Callable[[Path], dict[str, int]] = _default_sync,
        clock: Callable[[], float] = time.time,
        min_gap_s: float = MIN_GAP_S,
    ):
        self._dir, self._run, self._clock, self._gap = data_dir, run, clock, min_gap_s
        self._lock = threading.Lock()
        self._state: dict = {
            "running": False,
            "finished_at": None,
            "counts": None,
            "error": None,
        }
        self._stamp = data_dir / "sync_button.json"  # survives restarts
        self._started_at = self._load_started_at()

    def _load_started_at(self) -> float:
        try:
            return float(json.loads(self._stamp.read_text())["started_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return -1e18

    def _set_started_at(self, ts: float) -> None:
        self._started_at = ts
        try:
            self._stamp.write_text(json.dumps({"started_at": ts}))
        except OSError:
            pass  # the in-memory gap still applies

    def state(self) -> dict:
        with self._lock:
            return dict(self._state)

    def start(self) -> tuple[bool, str]:
        """Start a sync in a thread. Returns (started, reason when not started)."""
        with self._lock:
            if self._state["running"]:
                return False, "A sync is already running."
            wait = self._started_at + self._gap - self._clock()
            if wait > 0:
                return (
                    False,
                    f"Synced recently; try again in {int(wait // 60) + 1} min.",
                )
            self._set_started_at(self._clock())
            self._state.update(running=True, error=None)
        threading.Thread(target=self._work, daemon=True).start()
        return True, ""

    def _work(self) -> None:
        counts, error, retry_now = None, None, False
        try:
            counts = self._run(self._dir)
        except (
            NeedsLogin
        ):  # nothing was fetched: let the user retry right after `suunto login`
            error, retry_now = (
                "Suunto session expired. Run `uv run suunto login` in a terminal, then sync again.",
                True,
            )
        except (
            RuntimeError
        ) as exc:  # local setup problem (no suuntool): nothing reached Suunto
            error, retry_now = str(exc), True
        except (
            PoliteClientError
        ) as exc:  # Suunto pushed back (cooldown, cap, 403...): keep the gap
            error = str(exc)
        except Exception as exc:  # keep the server alive; details stay local
            error = f"Sync failed: {type(exc).__name__}"
        with self._lock:
            self._state.update(
                running=False, finished_at=self._clock(), counts=counts, error=error
            )
            if retry_now:
                self._set_started_at(-1e18)
