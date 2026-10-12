"""Read-only client for the Suunto app backend (undocumented; shapes from community docs).

Auth is injected via `SessionProvider`, so this module holds no credentials and no
login logic. Every call goes through `PoliteClient`. Raw responses are cached on disk
so parsing bugs never trigger re-fetches.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, Protocol

from suunto_analytics.core.http_client import PoliteClient

API_BASE = "https://api.sports-tracker.com/apiserver/v1/"
TIMELINE_BASE = "https://247.sports-tracker.com/v1/"
HONEST_UA = "suunto-analytics/0.1 (personal, read-only)"

Stream = Literal["sleep", "activity", "recovery", "sleepstages"]
STREAMS = ("sleep", "activity", "recovery", "sleepstages")
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SessionProvider(Protocol):
    def session_key(self) -> str:
        """Return a valid session key (value of the STTAuthorization header)."""


class SuuntoAppApi:
    def __init__(self, http: PoliteClient, session: SessionProvider, raw_dir: Path):
        self._http, self._session, self._raw = http, session, raw_dir

    def _headers(self) -> dict[str, str]:
        return {
            "STTAuthorization": self._session.session_key(),
            "User-Agent": HONEST_UA,
            "Accept-Language": "en",
        }

    def _cache(self, name: str, data: bytes) -> Path:
        self._raw.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self._raw / name
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return path

    def fetch_wellness(self, stream: Stream, since_ms: int) -> Path:
        """Download a 24/7 stream (gzipped NDJSON) since `since_ms`; returns the cached file."""
        if stream not in STREAMS or not isinstance(since_ms, int):
            raise ValueError(f"invalid stream or since: {stream!r}")
        resp = self._http.request(
            "GET",
            f"{TIMELINE_BASE}{stream}/export",
            params={"since": since_ms},
            headers=self._headers(),
        )
        return self._cache(f"{stream}_{since_ms}.ndjson.gz", resp.content)

    def list_workouts(self, **params) -> dict:
        resp = self._http.request(
            "GET", f"{API_BASE}workouts", params=params, headers=self._headers()
        )
        return resp.json()

    def fetch_fit(self, workout_key: str) -> Path:
        if not _SAFE_KEY.match(workout_key):
            raise ValueError("invalid workout key")
        resp = self._http.request(
            "GET", f"{API_BASE}workout/exportFit/{workout_key}", headers=self._headers()
        )
        return self._cache(f"workout_{workout_key}.fit", resp.content)


def read_ndjson_gz(path: Path) -> Iterator[dict]:
    """Stream records from a cached gzipped NDJSON file (constant memory)."""
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)
