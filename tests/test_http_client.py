import httpx
import pytest

from suunto_analytics.core.http_client import (
    CircuitOpen,
    Cooldown,
    CooldownActive,
    PoliteClient,
    RequestCapReached,
)


def make(tmp_path, statuses, **kw):
    calls = iter(statuses)
    sleeps: list[float] = []
    transport = httpx.MockTransport(lambda req: httpx.Response(next(calls)))
    client = PoliteClient(
        Cooldown(tmp_path / "cooldown.json"),
        transport=transport,
        sleep=sleeps.append,
        jitter=0.0,
        **kw,
    )
    return client, sleeps


def test_ok_and_throttle(tmp_path):
    c, sleeps = make(tmp_path, [200, 200], min_interval=2.0)
    c.request("GET", "https://x.test/a")
    c.request("GET", "https://x.test/b")
    assert c.requests_made == 2 and sleeps  # second call was throttled


@pytest.mark.parametrize("status", [401, 403, 429])
def test_circuit_breaker_and_persisted_cooldown(tmp_path, status):
    c, _ = make(tmp_path, [status, 200])
    with pytest.raises(CircuitOpen):
        c.request("GET", "https://x.test/a")
    with pytest.raises(CooldownActive):  # no network call is made
        c.request("GET", "https://x.test/a")
    assert c.requests_made == 1
    c2, _ = make(tmp_path, [200])  # new client, same cooldown file
    with pytest.raises(CooldownActive):
        c2.request("GET", "https://x.test/a")


def test_5xx_backoff_then_success(tmp_path):
    c, sleeps = make(tmp_path, [503, 502, 200])
    assert c.request("GET", "https://x.test/a").status_code == 200
    assert c.requests_made == 3 and sleeps


def test_5xx_gives_up_after_max_tries(tmp_path):
    c, _ = make(tmp_path, [500, 500, 500])
    with pytest.raises(httpx.HTTPStatusError):
        c.request("GET", "https://x.test/a")
    assert c.requests_made == 3


def test_request_cap(tmp_path):
    c, _ = make(tmp_path, [200, 200, 200], max_requests=2)
    c.request("GET", "https://x.test/a")
    c.request("GET", "https://x.test/b")
    with pytest.raises(RequestCapReached):
        c.request("GET", "https://x.test/c")
