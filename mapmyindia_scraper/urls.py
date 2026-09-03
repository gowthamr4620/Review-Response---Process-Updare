"""
Parsing of Mappls (MapmyIndia) listing links.

The input to this pipeline is whatever link the client pasted into a
spreadsheet cell, and those are never uniform. In practice they arrive as:

    https://mappls.com/<eloc>                       short link to a place
    https://maps.mappls.com/<eloc>
    https://mappls.com/place/<ELOC>/<slug>
    https://www.mapmyindia.com/...?eloc=<ELOC>      legacy domain
    https://<brand>.mappls.com/store/...            hosted store locator
    https://mappls.com/search/<query>@28.61,77.20,17z

An eLoc is Mappls' 6-character alphanumeric digital address. When we can pull
one out of the URL we can hit the official Place Details API directly and skip
HTML parsing entirely - that is the difference between a scraper that survives
a front-end redesign and one that does not, so it is worth the parsing effort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlunparse

MAPPLS_HOST_SUFFIXES = (".mappls.com", "mappls.com", ".mapmyindia.com", "mapmyindia.com")

_ELOC_RE = re.compile(r"^[A-Za-z0-9]{6}$")
_ELOC_QUERY_KEYS = ("eloc", "eLoc", "elocid", "placeid", "place_id", "place", "id", "mmi_eloc")

# 6-char path segments that are site vocabulary, not eLocs. Without this list a
# link like https://mappls.com/search/... would be "resolved" to eLoc "search".
_RESERVED_SEGMENTS = {
    "search", "places", "direct", "mobile", "static", "widget", "corpor",
    "signin", "signup", "sitemap", "hotels", "petrol", "nearby", "stores",
    "store", "about", "api", "maps", "place", "index", "assets", "images",
}

# Mappls map URLs carry the viewport as @lat,lng,zoom. That is the map centre,
# not necessarily the POI, so it is only ever used as a last-resort hint.
_AT_COORDS_RE = re.compile(r"@(-?\d{1,3}\.\d+),(-?\d{1,3}\.\d+)")

_TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_", "_ga")


@dataclass
class ParsedListingUrl:
    url: str
    host: str
    eloc: Optional[str] = None
    eloc_confidence: str = "none"      # "explicit" (query/path marker) | "guess" | "none"
    hint_latitude: Optional[float] = None
    hint_longitude: Optional[float] = None
    kind: str = "unknown"              # eloc | search | coordinates | page
    is_mappls_host: bool = False

    @property
    def api_ready(self) -> bool:
        """True when we can go straight to the Place Details API."""
        return bool(self.eloc)


def is_mappls_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == s.lstrip(".") or host.endswith(s) for s in MAPPLS_HOST_SUFFIXES)


def clean_url(url: str) -> str:
    """Drop tracking params and fragments so identical listings dedupe cleanly."""
    parts = urlparse(url.strip())
    query = parse_qs(parts.query, keep_blank_values=True)
    kept = {k: v for k, v in query.items() if not k.lower().startswith(_TRACKING_PREFIXES)}
    new_query = "&".join(f"{k}={v[0]}" for k, v in kept.items())
    return urlunparse((parts.scheme or "https", parts.netloc, parts.path, parts.params, new_query, ""))


def _eloc_from_query(query: str) -> Optional[str]:
    params = parse_qs(query)
    lowered = {k.lower(): v for k, v in params.items()}
    for key in _ELOC_QUERY_KEYS:
        values = lowered.get(key.lower())
        if values and _ELOC_RE.match(values[0].strip()):
            return values[0].strip().upper()
    return None


def _eloc_from_path(path: str) -> Tuple[Optional[str], str]:
    """Return (eloc, confidence). A segment right after /place/ is explicit."""
    segments = [s for s in path.split("/") if s]
    for i, segment in enumerate(segments):
        if segment.lower() in ("place", "eloc", "poi") and i + 1 < len(segments):
            candidate = segments[i + 1].split("@")[0]
            if _ELOC_RE.match(candidate):
                return candidate.upper(), "explicit"
    # Bare short link: https://mappls.com/<eloc>
    if len(segments) == 1:
        candidate = segments[0].split("@")[0]
        if _ELOC_RE.match(candidate) and candidate.lower() not in _RESERVED_SEGMENTS:
            return candidate.upper(), "guess"
    return None, "none"


def parse_listing_url(url: str) -> ParsedListingUrl:
    cleaned = clean_url(url)
    parts = urlparse(cleaned)
    host = (parts.hostname or "").lower()

    eloc = _eloc_from_query(parts.query)
    confidence = "explicit" if eloc else "none"
    if not eloc:
        eloc, confidence = _eloc_from_path(parts.path)

    lat = lng = None
    match = _AT_COORDS_RE.search(cleaned)
    if match:
        lat, lng = float(match.group(1)), float(match.group(2))

    if eloc:
        kind = "eloc"
    elif "/search" in parts.path.lower():
        kind = "search"
    elif lat is not None:
        kind = "coordinates"
    else:
        kind = "page"

    return ParsedListingUrl(
        url=cleaned,
        host=host,
        eloc=eloc,
        eloc_confidence=confidence,
        hint_latitude=lat,
        hint_longitude=lng,
        kind=kind,
        is_mappls_host=is_mappls_url(cleaned),
    )
