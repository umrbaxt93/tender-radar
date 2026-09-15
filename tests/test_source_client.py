"""Rate limiting, backoff and the hard stops in the public source client."""

from __future__ import annotations

import random

import httpx
import pytest

from radar.source.client import (
    BACKOFF_SECONDS,
    MIN_INTERVAL_S,
    HttpSource,
    RateLimiter,
    SourceBlocked,
    SourceError,
    SourcePaused,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_rate_limiter_never_goes_faster_than_three_seconds():
    clock = Clock()
    limiter = RateLimiter(interval=3.0, jitter=1.0, sleep=clock.sleep, clock=clock.monotonic,
                          rng=random.Random(0))
    assert limiter.wait() == 0.0  # first call is immediate
    for _ in range(20):
        waited = limiter.wait()
        assert MIN_INTERVAL_S <= waited <= MIN_INTERVAL_S + 1.0


def test_configured_interval_can_only_be_slower():
    clock = Clock()
    fast = RateLimiter(interval=0.1, sleep=clock.sleep, clock=clock.monotonic)
    assert fast.interval == MIN_INTERVAL_S
    slow = RateLimiter(interval=10, sleep=clock.sleep, clock=clock.monotonic)
    assert slow.interval == 10


def build(handler, clock: Clock, **kwargs) -> HttpSource:
    client = httpx.Client(transport=httpx.MockTransport(handler),
                          headers={"User-Agent": "test"}, follow_redirects=False)
    return HttpSource("https://example.invalid/list", "https://example.invalid/detail/{source_id}",
                      "ops@example.invalid", client=client, sleep=clock.sleep,
                      limiter=RateLimiter(sleep=clock.sleep, clock=clock.monotonic), **kwargs)


def test_user_agent_carries_the_contact_email():
    source = HttpSource("https://a.invalid/l", "https://a.invalid/d/{source_id}",
                        "ops@example.invalid")
    assert "ops@example.invalid" in source.client.headers["user-agent"]


def test_missing_configuration_is_refused():
    with pytest.raises(SourceError):
        HttpSource("", "", "ops@example.invalid")
    with pytest.raises(SourceError):
        HttpSource("https://a.invalid/l", "https://a.invalid/d", "")


def test_successful_json_response():
    clock = Clock()
    source = build(lambda req: httpx.Response(200, json={"data": {"items": []}},
                                              headers={"content-type": "application/json"}),
                   clock)
    fetched = source.list_page(1)
    assert b"items" in fetched.body


def test_403_stops_collection_without_retrying():
    clock = Clock()
    source = build(lambda req: httpx.Response(403, text="forbidden"), clock)
    with pytest.raises(SourceBlocked):
        source.list_page(1)
    assert clock.slept == [], "a block must not be retried"


def test_redirect_to_a_login_page_stops_collection():
    clock = Clock()
    source = build(lambda req: httpx.Response(302, headers={"location": "/login"}), clock)
    with pytest.raises(SourceBlocked):
        source.list_page(1)


def test_captcha_body_stops_collection():
    clock = Clock()
    source = build(lambda req: httpx.Response(200, text="<html><form>CAPTCHA</form></html>",
                                              headers={"content-type": "text/html"}), clock)
    with pytest.raises(SourceBlocked):
        source.list_page(1)


def test_backoff_sequence_then_pause():
    clock = Clock()
    source = build(lambda req: httpx.Response(503, text="busy"), clock)
    with pytest.raises(SourcePaused) as exc:
        source.list_page(1)
    assert clock.slept[:4] == list(BACKOFF_SECONDS[:4])
    assert "cursor persisted" in str(exc.value)


def test_recovery_after_one_failure_resets_the_counter():
    clock = Clock()
    responses = [httpx.Response(429, text="slow down"),
                 httpx.Response(200, json={"ok": True},
                                headers={"content-type": "application/json"})]
    source = build(lambda req: responses.pop(0), clock)
    assert source.list_page(1).body
    assert clock.slept == [BACKOFF_SECONDS[0]]
    assert source.consecutive_failures == 0


def test_network_errors_are_retried_then_paused():
    clock = Clock()

    def handler(request):
        raise httpx.ConnectError("no route")

    source = build(handler, clock)
    with pytest.raises(SourcePaused):
        source.list_page(1)


def test_detail_url_templating():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json={}, headers={"content-type": "application/json"})

    build(handler, Clock()).detail("ABC-1")
    assert seen["url"].endswith("/detail/ABC-1")


class _Resp:
    """Minimal stand-in for a requests Response."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.headers = {"content-type": "application/json"}
        self.text = "{}"

    def json(self):
        return [{"ok": True}]


class _Sequence:
    """Answers with each status in turn, then 200 forever."""

    def __init__(self, *statuses: int) -> None:
        self.statuses = list(statuses)
        self.calls = 0

    def __call__(self, *args, **kwargs) -> _Resp:
        self.calls += 1
        return _Resp(self.statuses.pop(0) if self.statuses else 200)


def test_uzex_paces_every_attempt_including_retries(monkeypatch):
    """A retry is a fresh request to a host that just asked us to slow down. Pacing only
    the first attempt left retries 2 s apart, under the floor CLAUDE.md makes mandatory."""
    import time as _time

    from radar.source.uzex import UzexClient

    monkeypatch.setattr(_time, "sleep", lambda s: None)   # skip the adapter's own backoff
    clock = Clock()
    client = UzexClient(limiter=RateLimiter(sleep=clock.sleep, clock=clock.monotonic,
                                            rng=random.Random(0)))
    post = _Sequence(429, 503)                            # two rejections, then success
    client.session.post = post

    client._request("POST", "https://example.invalid/x", json_data={})

    assert post.calls == 3                                # it did retry
    assert len(clock.slept) == 2                          # and paced both retries
    assert all(gap >= MIN_INTERVAL_S for gap in clock.slept)


def test_uzex_paces_separate_requests():
    from radar.source.uzex import UzexClient

    clock = Clock()
    client = UzexClient(limiter=RateLimiter(sleep=clock.sleep, clock=clock.monotonic,
                                            rng=random.Random(0)))
    client.session.post = lambda *a, **k: _Resp()

    for _ in range(4):
        client._request("POST", "https://example.invalid/x", json_data={})

    assert len(clock.slept) == 3                          # the first call is immediate
    assert all(gap >= MIN_INTERVAL_S for gap in clock.slept)


def test_ebirja_paces_every_attempt_including_retries(monkeypatch):
    import time as _time
    import urllib.error

    from radar.source import ebirja as ebirja_mod
    from radar.source.ebirja import EbirjaClient

    monkeypatch.setattr(_time, "sleep", lambda s: None)
    calls = {"n": 0}

    def fake_urlopen(req, **kwargs):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(ebirja_mod.urllib.request, "urlopen", fake_urlopen)
    clock = Clock()
    client = EbirjaClient(limiter=RateLimiter(sleep=clock.sleep, clock=clock.monotonic,
                                              rng=random.Random(0)))

    client._request("/common/contract/shop-list", {"type": "e-shop"})

    assert calls["n"] == 3                                # default retries
    assert len(clock.slept) == 2                          # every retry went through the limiter
    assert all(gap >= MIN_INTERVAL_S for gap in clock.slept)


def test_source_adapters_verify_tls_certificates():
    import ssl

    from radar.source.ebirja import EbirjaClient
    from radar.source.uzex import UzexClient

    assert UzexClient().session.verify is True
    assert EbirjaClient().ctx.verify_mode == ssl.CERT_REQUIRED


def test_uzex_sends_no_reverse_engineered_validation_header():
    """The Validation header was built from an RSA key lifted out of the site's JS bundle.
    Live checks showed the endpoints answer identically without it, so it is gone."""
    from radar.source.uzex import UzexClient

    assert "Validation" not in UzexClient()._get_headers()
