"""
Polite HTTP client for the scraper.

Three behaviours here are not optional extras, they are what keeps this tool
usable and defensible:

1. Rate limiting. One request per second by default. Mappls returns HTTP 403
   when you exceed your rate limit, and a burst-y scraper gets an IP banned
   long before it finishes a list of stores.
2. robots.txt. Checked once per host and honoured by default. If a path is
   disallowed the fetch fails loudly with the reason instead of quietly
   proceeding - you should be making that call consciously, per site.
3. An on-disk response cache. Verification gets re-run (thresholds change,
   the sheet gets corrected); re-running it should not mean re-hitting the
   site. Cached responses also give you a reproducible input when a result
   looks wrong.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency is declared
    raise SystemExit(
        "mapmyindia_scraper needs 'requests'. Install with: pip install -r "
        "mapmyindia_scraper/requirements.txt"
    ) from exc

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class RobotsDisallowed(RuntimeError):
    """Raised when robots.txt forbids the URL and --ignore-robots was not set."""


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    content_type: str = ""
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type.lower()


class HttpClient:
    def __init__(
        self,
        rate_per_sec: float = 1.0,
        timeout: float = 30.0,
        retries: int = 3,
        cache_dir: Optional[str] = None,
        user_agent: str = DEFAULT_USER_AGENT,
        respect_robots: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.min_interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self.timeout = timeout
        self.retries = retries
        self.cache_dir = cache_dir
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        self._last_request_at = 0.0
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-IN,en;q=0.9",
                **(extra_headers or {}),
            }
        )
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    # ---------------------------------------------------------------- cache

    def _cache_path(self, method: str, url: str, body: Optional[str]) -> str:
        key = hashlib.sha256(f"{method}|{url}|{body or ''}".encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{key}.json")

    def _read_cache(self, path: str) -> Optional[FetchResult]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return None
        return FetchResult(
            url=data["url"],
            final_url=data.get("final_url", data["url"]),
            status=data.get("status", 200),
            text=data.get("text", ""),
            content_type=data.get("content_type", ""),
            from_cache=True,
        )

    def _write_cache(self, path: str, result: FetchResult) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "url": result.url,
                    "final_url": result.final_url,
                    "status": result.status,
                    "content_type": result.content_type,
                    "text": result.text,
                },
                f,
            )
        os.replace(tmp, path)

    # --------------------------------------------------------------- robots

    def _robots_for(self, url: str) -> Optional[RobotFileParser]:
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser = RobotFileParser()
        try:
            response = self.session.get(urljoin(origin, "/robots.txt"), timeout=self.timeout)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            else:
                parser = None  # no robots.txt served -> nothing to honour
        except requests.RequestException:
            parser = None
        self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    # ---------------------------------------------------------------- fetch

    def _throttle(self) -> None:
        if self.min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def request(
        self,
        url: str,
        method: str = "GET",
        data: Optional[dict] = None,
        headers: Optional[Dict[str, str]] = None,
        use_cache: bool = True,
    ) -> FetchResult:
        cache_path = None
        if self.cache_dir and use_cache and method == "GET":
            cache_path = self._cache_path(method, url, None)
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached

        if method == "GET" and not self.allowed(url):
            raise RobotsDisallowed(f"robots.txt disallows {url} (re-run with --ignore-robots to override)")

        last_error: Optional[str] = None
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                response = self.session.request(
                    method, url, data=data, headers=headers, timeout=self.timeout, allow_redirects=True
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                self._backoff(attempt)
                continue

            if response.status_code in RETRY_STATUSES and attempt < self.retries:
                last_error = f"HTTP {response.status_code}"
                self._backoff(attempt, response.headers.get("Retry-After"))
                continue

            result = FetchResult(
                url=url,
                final_url=response.url,
                status=response.status_code,
                text=response.text,
                content_type=response.headers.get("Content-Type", ""),
            )
            if cache_path and result.ok:
                self._write_cache(cache_path, result)
            return result

        raise requests.RequestException(f"giving up on {url} after {self.retries + 1} attempts: {last_error}")

    def get(self, url: str, **kwargs) -> FetchResult:
        return self.request(url, "GET", **kwargs)

    def _backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(min(60.0, float(retry_after)))
                return
            except ValueError:
                pass
        # Exponential with jitter: 2s, 4s, 8s ... plus up to 1s of noise so
        # parallel runs do not resynchronise onto the same retry instant.
        time.sleep(min(30.0, 2 ** (attempt + 1)) + random.random())
