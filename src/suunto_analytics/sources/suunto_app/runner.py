"""Runs the user's own `suuntool` binary politely (throttled, capped, circuit breaker).

suuntool owns the login/session; we never handle app keys. Exit codes (suuntool):
0 ok, 3 network, 4 auth expired, 5 server, 6 not found, 7 forbidden.
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from suunto_analytics.core.credentials import CredentialStore
from suunto_analytics.core.http_client import (
    CircuitOpen,
    Cooldown,
    PoliteClientError,
    RequestCapReached,
)

EXIT_NETWORK, EXIT_AUTH, EXIT_SERVER, EXIT_NOT_FOUND, EXIT_FORBIDDEN = 3, 4, 5, 6, 7


def find_suuntool() -> Path | None:
    """The user's suuntool binary: $SUUNTOOL_BIN, then PATH, then ~/suuntool-bin/suuntool."""
    for cand in (
        os.environ.get("SUUNTOOL_BIN"),
        shutil.which("suuntool"),
        str(Path.home() / "suuntool-bin" / "suuntool"),
    ):
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


class NeedsLogin(PoliteClientError):
    """Session expired and no stored credentials (run `suunto login`)."""


class NotFound(PoliteClientError):
    pass


class SuuntoolError(PoliteClientError):
    pass


class SuuntoolRunner:
    def __init__(
        self,
        binary: Path,
        cooldown: Cooldown,
        creds: CredentialStore,
        *,
        min_interval: float = 3.0,
        jitter: float = 2.0,
        max_calls: int = 60,
        max_tries: int = 3,
        cooldown_seconds: float = 24 * 3600,
        short_cooldown_seconds: int = 3600,
        session_file: Path | None = None,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._bin, self._cooldown, self._creds = str(binary), cooldown, creds
        self._min, self._jitter, self._max_calls, self._max_tries = (
            min_interval,
            jitter,
            max_calls,
            max_tries,
        )
        self._cd_seconds, self._short_cd = cooldown_seconds, short_cooldown_seconds
        self._run, self._sleep, self._clock = run, sleep, clock
        self._env = dict(os.environ)
        if session_file:
            self._env["SUUNTOOL_SESSION_FILE"] = str(session_file)
        self._calls, self._last, self._relogged = 0, -1e18, False

    @property
    def calls_made(self) -> int:
        return self._calls

    def login(self, email: str, password: str) -> None:
        """One login attempt, password via stdin only. Never retried."""
        self._cooldown.check()
        p = self._exec(["login", "--email", email, "--password-stdin"], stdin=password)
        if p.returncode != 0:
            if p.returncode in (EXIT_AUTH, EXIT_FORBIDDEN):
                self._cooldown.start(self._cd_seconds)
            raise SuuntoolError(f"login failed (exit {p.returncode})")

    def call(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a read-only suuntool command with throttling, backoff and the circuit breaker."""
        self._cooldown.check()
        for attempt in range(1, self._max_tries + 1):
            p = self._exec(args)
            rc = p.returncode
            if rc == 0:
                return p
            if rc == EXIT_AUTH:
                self._relogin_once()
                continue
            if rc == EXIT_FORBIDDEN:
                self._cooldown.start(self._cd_seconds)
                raise CircuitOpen(403)
            if rc == EXIT_NOT_FOUND:
                raise NotFound(" ".join(args[:3]))
            if attempt < self._max_tries:  # network / server: bounded backoff
                self._sleep(
                    min(60.0, 5.0 * 2 ** (attempt - 1))
                    + random.uniform(0, self._jitter)
                )
                continue
            # Unknown/persistent failure (could be throttling): stop everything for a while.
            self._cooldown.start(self._short_cd)
            raise SuuntoolError(
                f"{args[0]} failed (exit {rc}); cooling down {self._short_cd // 60} min"
            )
        raise SuuntoolError("gave up")

    def _relogin_once(self) -> None:
        """Session expired: a single silent re-login from the keychain, once per run."""
        creds = self._creds.get()
        if self._relogged or not creds:
            raise NeedsLogin("session expired; run `suunto login`")
        self._relogged = True
        self.login(*creds)

    def _exec(
        self, args: list[str], stdin: str | None = None
    ) -> subprocess.CompletedProcess:
        if self._calls >= self._max_calls:
            raise RequestCapReached(f"cap of {self._max_calls} suuntool calls reached")
        wait = self._last + self._min + random.uniform(0, self._jitter) - self._clock()
        if wait > 0:
            self._sleep(wait)
        self._last = self._clock()
        self._calls += 1
        try:
            return self._run(
                [self._bin, *args],
                input=stdin,
                capture_output=True,
                text=True,
                env=self._env,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise SuuntoolError(f"{args[0]} timed out") from exc
