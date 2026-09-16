"""Sources: a rate-limited public HTTP client and a fixture-directory source.

Hard constraints from docs/SPEC.md and DECISIONS.md:
  * one request every 3 s plus 0-1 s jitter (never faster), single worker;
  * User-Agent carries CONTACT_EMAIL;
  * 429/5xx backoff 10 -> 20 -> 40 -> 80 -> 160 s; after 5 consecutive failures the
    importer persists its cursor and exits (SourcePaused) instead of sleeping 30 min;
  * 403 / CAPTCHA / login pages stop collection immediately (SourceBlocked);
  * public pages only: no cookies, tokens, E-IMZO or CAPTCHA bypass.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

BACKOFF_SECONDS = (10, 20, 40, 80, 160)
MIN_INTERVAL_S = 3.0
MAX_JITTER_S = 1.0
BLOCK_MARKERS = (b"captcha", b"e-imzo", b"eimzo", b"<form", b"login")


class SourceError(RuntimeError):
    """Base class for source failures."""


class SourceBlocked(SourceError):
    """403 / CAPTCHA / login wall: stop collection, never bypass."""


class SourcePaused(SourceError):
    """Five consecutive retryable failures: persist cursor and exit."""


@dataclass(frozen=True)
class Fetched:
    url: str
    body: bytes


class Source(Protocol):
    name: str

    def list_page(self, page: int) -> Fetched: ...

    def detail(self, source_id: str) -> Fetched: ...


class RateLimiter:
    """Blocking limiter: at least MIN_INTERVAL_S + jitter between calls."""

    def __init__(self, interval: float = MIN_INTERVAL_S, jitter: float = MAX_JITTER_S,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None) -> None:
        self.interval = max(interval, MIN_INTERVAL_S)
        self.jitter = jitter
        self._sleep = sleep
        self._clock = clock
        self._rng = rng or random.Random()
        self._last: float | None = None

    def wait(self) -> float:
        wait_for = 0.0
        if self._last is not None:
            target = self._last + self.interval + self._rng.uniform(0, self.jitter)
            wait_for = max(0.0, target - self._clock())
            if wait_for > 0:
                self._sleep(wait_for)
        self._last = self._clock()
        return wait_for


class HttpSource:
    """Public JSON endpoints. URLs are operator-configured (docs/SOURCE_API.md)."""

    name = "uzex"

    def __init__(self, list_url: str, detail_url: str, contact_email: str,
                 list_params: dict | None = None, mapping: dict | None = None,
                 limiter: RateLimiter | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 client: httpx.Client | None = None) -> None:
        if not list_url or not detail_url:
            raise SourceError("UZEX_LIST_URL / UZEX_DETAIL_URL are not configured; "
                              "the public endpoint contract is unverified (docs/SOURCE_API.md)")
        if not contact_email:
            raise SourceError("CONTACT_EMAIL is required in the User-Agent")
        self.list_url = list_url
        self.detail_url = detail_url
        self.list_params = dict(list_params or {})
        self.mapping = mapping
        self.limiter = limiter or RateLimiter()
        self._sleep = sleep
        self.consecutive_failures = 0
        self.client = client or httpx.Client(
            headers={"User-Agent": f"tender-radar/0.1 (+{contact_email})",
                     "Accept": "application/json"},
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        )

    def _page_params(self, page: int) -> dict:
        spec = (self.mapping or {}).get("list", {})
        params = dict(self.list_params)
        page_param = spec.get("page_param", "page")
        page_size_param = spec.get("page_size_param", "size")
        page_size = spec.get("page_size")
        first_page = spec.get("first_page", 1)
        if spec.get("range_pagination") or (page_param == "from" and page_size_param == "to"):
            sz = page_size or 50
            params[page_param] = (page - first_page) * sz + 1
            params[page_size_param] = (page - first_page + 1) * sz
        else:
            params[page_param] = page
            if page_size:
                params[page_size_param] = page_size
        return params

    def list_page(self, page: int) -> Fetched:
        spec = (self.mapping or {}).get("list", {})
        method = spec.get("method", "GET").upper()
        params = self._page_params(page)
        if method == "POST":
            return self._request("POST", self.list_url, json_data=params)
        return self._request("GET", self.list_url, params=params)

    def detail(self, source_id: str) -> Fetched:
        spec = (self.mapping or {}).get("detail", {})
        method = spec.get("method", "GET").upper()
        url = self.detail_url.format(source_id=source_id, id=source_id)
        params = (None if ("{source_id}" in self.detail_url or "{id}" in self.detail_url)
                  else {"id": source_id})
        if method == "POST":
            return self._request("POST", url, json_data=params)
        return self._request("GET", url, params=params)

    def _get(self, url: str, params: dict | None) -> Fetched:
        return self._request("GET", url, params=params)

    def _request(self, method: str, url: str, params: dict | None = None,
                 json_data: dict | None = None) -> Fetched:
        attempt = 0
        while True:
            self.limiter.wait()
            try:
                resp = self.client.request(method, url, params=params, json=json_data)
            except httpx.HTTPError as exc:
                self._retry_or_pause(attempt, f"network error: {type(exc).__name__}")
                attempt += 1
                continue
            final_url = str(resp.request.url)
            if resp.status_code in (401, 403) or resp.status_code in (301, 302, 303, 307, 308):
                raise SourceBlocked(f"{resp.status_code} from {final_url}: stopping (no bypass)")
            if resp.status_code == 429 or resp.status_code >= 500:
                self._retry_or_pause(attempt, f"HTTP {resp.status_code}")
                attempt += 1
                continue
            if resp.status_code != 200:
                raise SourceError(f"HTTP {resp.status_code} from {final_url}")
            body = resp.content
            head = body[:4096].lower()
            ctype = resp.headers.get("content-type", "")
            if "json" not in ctype and any(m in head for m in BLOCK_MARKERS):
                raise SourceBlocked(f"non-JSON login/CAPTCHA page from {final_url}")
            self.consecutive_failures = 0
            return Fetched(url=final_url, body=body)

    def _retry_or_pause(self, attempt: int, reason: str) -> None:
        self.consecutive_failures += 1
        if attempt >= len(BACKOFF_SECONDS) or self.consecutive_failures >= 5:
            raise SourcePaused(f"{self.consecutive_failures} consecutive failures ({reason}); "
                               "cursor persisted, exiting")
        delay = BACKOFF_SECONDS[attempt]
        log.warning("source %s, backing off %ss (attempt %d)", reason, delay, attempt + 1)
        self._sleep(delay)


class FixtureSource:
    """Reads list_page_<n>.json / detail_<id>.json from a directory (tests, synthetic runs)."""

    def __init__(self, directory: str | Path, limiter: RateLimiter | None = None,
                 name: str = "synthetic") -> None:
        self.name = name  # rows imported from fixtures are labelled, never "uzex"
        self.dir = Path(directory)
        if not self.dir.is_dir():
            raise SourceError(f"fixture directory {self.dir} does not exist")
        self.limiter = limiter  # None: no throttling for local files

    def _read(self, name: str) -> Fetched:
        if self.limiter:
            self.limiter.wait()
        path = self.dir / name
        if not path.is_file():
            raise SourceError(f"fixture {path} missing")
        return Fetched(url=f"fixture://{self.dir.name}/{name}", body=path.read_bytes())

    def list_page(self, page: int) -> Fetched:
        if not (self.dir / f"list_page_{page}.json").is_file():
            # past the last page: behave like an empty listing
            return Fetched(url=f"fixture://{self.dir.name}/list_page_{page}.json",
                           body=b'{"data": {"items": []}}')
        return self._read(f"list_page_{page}.json")

    def detail(self, source_id: str) -> Fetched:
        return self._read(f"detail_{source_id}.json")
