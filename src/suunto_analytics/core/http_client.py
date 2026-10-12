"""PoliteClient: the only way to call Suunto's unofficial backend.

Serial requests, throttle + jitter, per-run cap, bounded backoff on 5xx, and a
circuit breaker (401/403/429 abort the run and start a persisted cooldown).
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from pathlib import Path

import httpx

COOLDOWN_STATUSES = frozenset({401, 403, 429})


class PoliteClientError(Exception):
    """Base error."""


class CooldownActive(PoliteClientError):
    def __init__(self, until: float):
        super().__init__(
            f"cooldown active until {time.strftime('%F %T', time.localtime(until))}"
        )
        self.until = until


class RequestCapReached(PoliteClientError):
    pass


class CircuitOpen(PoliteClientError):
    """Raised on 401/403/429; a cooldown has been recorded."""

    def __init__(self, status: int):
        super().__init__(f"HTTP {status}: aborting run and entering cooldown")
        self.status = status


class Cooldown:
    """Persisted cooldown deadline (survives restarts)."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self._path, self._clock = path, clock

    def until(self) -> float:
        try:
            return float(json.loads(self._path.read_text())["until"])
        except (OSError, ValueError, KeyError):
            return 0.0

    def check(self) -> None:
        until = self.until()
        if until > self._clock():
            raise CooldownActive(until)

    def start(self, seconds: float) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"until": self._clock() + seconds}))
        self._path.chmod(0o600)


class PoliteClient:
    def __init__(
        self,
        cooldown: Cooldown,
        *,
        min_interval: float = 2.0,
        jitter: float = 1.0,
        max_requests: int = 200,
        max_tries: int = 3,
        cooldown_seconds: float = 24 * 3600,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        headers: dict[str, str] | None = None,
    ):
        self._cooldown = cooldown
        self._min_interval, self._jitter = min_interval, jitter
        self._max_requests, self._max_tries = max_requests, max_tries
        self._cooldown_seconds = cooldown_seconds
        self._sleep, self._clock = sleep, clock
        self._http = httpx.Client(timeout=timeout, transport=transport, headers=headers)
        self._count = 0
        self._last = -1e18

    @property
    def requests_made(self) -> int:
        return self._count

    def close(self) -> None:
        self._http.close()

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self._cooldown.check()
        for attempt in range(1, self._max_tries + 1):
            if self._count >= self._max_requests:
                raise RequestCapReached(f"cap of {self._max_requests} requests reached")
            self._throttle()
            self._count += 1
            resp = self._http.request(method, url, **kwargs)
            if resp.status_code in COOLDOWN_STATUSES:
                self._cooldown.start(self._cooldown_seconds)
                raise CircuitOpen(resp.status_code)
            if resp.status_code >= 500 and attempt < self._max_tries:
                self._sleep(
                    min(60.0, 5.0 * 2 ** (attempt - 1))
                    + random.uniform(0, self._jitter)
                )
                continue
            resp.raise_for_status()
            return resp
        raise PoliteClientError("unreachable")  # pragma: no cover

    def _throttle(self) -> None:
        wait = (
            self._last
            + self._min_interval
            + random.uniform(0, self._jitter)
            - self._clock()
        )
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()
