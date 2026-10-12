import gzip
import json

import httpx

from suunto_analytics.core.http_client import Cooldown, PoliteClient
from suunto_analytics.sources.suunto_app.api import (
    HONEST_UA,
    SuuntoAppApi,
    read_ndjson_gz,
)


class FakeSession:
    def session_key(self) -> str:
        return "test-key"


def make_api(tmp_path, handler):
    http = PoliteClient(
        Cooldown(tmp_path / "cd.json"),
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        jitter=0.0,
    )
    return SuuntoAppApi(http, FakeSession(), tmp_path / "raw")


def test_wellness_cached_and_parsed(tmp_path):
    body = gzip.compress(b'{"a": 1}\n\n{"a": 2}\n')
    seen = {}

    def handler(req: httpx.Request):
        seen.update(
            url=str(req.url),
            auth=req.headers["STTAuthorization"],
            ua=req.headers["User-Agent"],
        )
        return httpx.Response(200, content=body)

    path = make_api(tmp_path, handler).fetch_wellness("sleep", 123)
    assert seen["url"] == "https://247.sports-tracker.com/v1/sleep/export?since=123"
    assert seen["auth"] == "test-key" and seen["ua"] == HONEST_UA
    assert [r["a"] for r in read_ndjson_gz(path)] == [1, 2]


def test_fit_and_list(tmp_path):
    def handler(req: httpx.Request):
        if "exportFit" in req.url.path:
            return httpx.Response(200, content=b"FITDATA")
        return httpx.Response(200, json={"payload": []})

    api = make_api(tmp_path, handler)
    assert api.fetch_fit("abc").read_bytes() == b"FITDATA"
    assert api.list_workouts(limit=5) == {"payload": []}


def test_rejects_unsafe_keys_and_cache_is_private(tmp_path):
    import pytest

    api = make_api(tmp_path, lambda req: httpx.Response(200, content=b"x"))
    for bad in ("../evil", "a/b", "", "a" * 65):
        with pytest.raises(ValueError):
            api.fetch_fit(bad)
    with pytest.raises(ValueError):
        api.fetch_wellness("../x", 1)  # type: ignore[arg-type]
    p = api.fetch_fit("ok_key-1")
    assert oct(p.stat().st_mode & 0o777) == "0o600"
