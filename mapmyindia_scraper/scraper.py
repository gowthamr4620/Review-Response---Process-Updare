"""
Orchestration: one listing URL in, one Listing out.

The resolution order is a deliberate quality ladder, best source first:

  1. Official Mappls API, when the URL yields an eLoc and credentials exist.
     Structured, licensed, stable.
  2. The page's own HTML (JSON-LD / embedded app state / meta / text).
     Needed for brand-hosted store-locator pages that never expose an eLoc.
  3. A headless browser render, only if you ask for it (--browser). Mappls'
     map UI is client-rendered, so a plain GET can come back as an empty
     shell; rendering costs ~2-4s per URL and is the honest fix for that.
  4. Coordinates parsed out of the URL's @lat,lng - map viewport, not the POI.
     Recorded with source "url-hint" so it is never mistaken for a real value.

Every step only fills fields still blank, so a weaker source can complete a
record but never overwrite a stronger one.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Iterable, Iterator, List, Optional

from .api import MapplsApiClient, MapplsApiError
from .extract import extract_listing_from_html, extract_listing_from_json
from .http_client import HttpClient, RobotsDisallowed
from .models import Listing
from .urls import ParsedListingUrl, parse_listing_url

# A page that is really a JS shell yields nothing but a title; if fewer than
# this many core fields come back, a browser render is worth trying.
_MIN_FIELDS_BEFORE_BROWSER = 2


class ListingScraper:
    def __init__(
        self,
        http: Optional[HttpClient] = None,
        api: Optional[MapplsApiClient] = None,
        use_api: bool = True,
        use_browser: bool = False,
        raw_dir: Optional[str] = None,
        verbose: bool = True,
    ) -> None:
        self.http = http or HttpClient()
        self.api = api or MapplsApiClient(http=self.http)
        self.use_api = use_api
        self.use_browser = use_browser
        self.raw_dir = raw_dir
        self.verbose = verbose
        if raw_dir:
            os.makedirs(raw_dir, exist_ok=True)

    # ------------------------------------------------------------- helpers

    def _log(self, message: str) -> None:
        if self.verbose:
            print(message, flush=True)

    def _dump_raw(self, listing: Listing, body: str, suffix: str) -> None:
        if not self.raw_dir or not body:
            return
        name = (listing.eloc or str(abs(hash(listing.source_url))))[:40]
        path = os.path.join(self.raw_dir, f"{name}.{suffix}")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        listing.raw_path = path

    @staticmethod
    def _core_field_count(listing: Listing) -> int:
        return sum(
            1
            for name in ("business_name", "address", "pincode", "latitude", "phone")
            if listing.get(name) not in (None, "")
        )

    # -------------------------------------------------------------- stages

    def _from_api(self, parsed: ParsedListingUrl, listing: Listing) -> None:
        if not (self.use_api and parsed.eloc and self.api.configured):
            return
        try:
            api_listing = self.api.listing_for_eloc(parsed.eloc, parsed.url)
            listing.fill_from(api_listing, "mappls-api")
            listing.strategies_tried.append("mappls-api")
        except MapplsApiError as exc:
            # Not fatal: fall through to HTML and record why the API was no help.
            listing.strategies_tried.append(f"mappls-api-failed({exc})")
            self._log(f"    api: {exc}")

    def _from_html(self, parsed: ParsedListingUrl, listing: Listing) -> None:
        result = self.http.get(parsed.url)
        if not result.ok:
            raise RuntimeError(f"HTTP {result.status} fetching {parsed.url}")
        self._dump_raw(listing, result.text, "json" if result.is_json else "html")
        if result.is_json:
            import json

            extract_listing_from_json(json.loads(result.text), parsed.url, "page-json", listing)
        else:
            extract_listing_from_html(result.text, parsed.url, listing)

    def _from_browser(self, parsed: ParsedListingUrl, listing: Listing) -> None:
        html = render_with_browser(parsed.url)
        if not html:
            return
        self._dump_raw(listing, html, "rendered.html")
        extract_listing_from_html(html, parsed.url, listing)
        listing.strategies_tried.append("browser-render")

    # ---------------------------------------------------------------- main

    def scrape(self, url: str) -> Listing:
        parsed = parse_listing_url(url)
        listing = Listing(source_url=parsed.url, eloc=parsed.eloc)
        if parsed.eloc:
            listing.field_sources["eloc"] = f"url({parsed.eloc_confidence})"
        listing.fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        try:
            self._from_api(parsed, listing)

            if self._core_field_count(listing) < len(("business_name", "address")):
                self._from_html(parsed, listing)

            if self.use_browser and self._core_field_count(listing) < _MIN_FIELDS_BEFORE_BROWSER:
                self._from_browser(parsed, listing)

            if listing.latitude is None and parsed.hint_latitude is not None:
                listing.latitude, listing.longitude = parsed.hint_latitude, parsed.hint_longitude
                listing.field_sources["latitude"] = "url-hint"
                listing.field_sources["longitude"] = "url-hint"

            if not listing.has_any_data:
                listing.error = (
                    "no fields extracted - the page is probably client-rendered; "
                    "retry with --browser, or supply Mappls API credentials"
                )
        except RobotsDisallowed as exc:
            listing.error = str(exc)
        except Exception as exc:  # keep one bad row from killing a 500-row run
            listing.error = f"{type(exc).__name__}: {exc}"

        return listing

    def scrape_many(self, urls: Iterable[str]) -> Iterator[Listing]:
        urls = list(urls)
        for i, url in enumerate(urls, start=1):
            self._log(f"[{i}/{len(urls)}] {url}")
            started = time.monotonic()
            listing = self.scrape(url)
            status = listing.error or (
                f"{listing.business_name or '?'} | pin={listing.pincode or '-'} | phone={listing.phone or '-'}"
            )
            self._log(f"    -> {status}  ({time.monotonic() - started:.1f}s)")
            yield listing


def render_with_browser(url: str, timeout_ms: int = 30_000, wait_ms: int = 2_500) -> Optional[str]:
    """
    Render a client-side page with Playwright, if it is installed.

    Kept optional and isolated: the whole pipeline works without it, and the
    dependency only earns its place on pages that genuinely need JS.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    browser render requested but playwright is not installed "
              "(pip install playwright && playwright install chromium)", flush=True)
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(locale="en-IN")
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(wait_ms)  # let the map/detail XHRs settle
            return page.content()
        finally:
            browser.close()


def load_urls_from_file(path: str) -> List[str]:
    """One URL per line; blank lines and # comments ignored."""
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]
