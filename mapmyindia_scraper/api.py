"""
Client for the official Mappls (MapmyIndia) REST APIs.

This is the sanctioned way to get this data and it should be your default.
Mappls' terms prohibit scraping their web properties; the API has a free
tier, returns structured fields instead of markup, and does not break when
the site is redesigned. The HTML path in scraper.py exists for links the API
cannot resolve (hosted store-locator pages on brand domains, mostly) - not as
a way around getting credentials.

Endpoints used (all overridable via the Endpoints dataclass, because Mappls
has moved these before):

  POST https://outpost.mappls.com/api/security/oauth/token
       grant_type=client_credentials, client_id, client_secret -> access_token
  GET  https://place.mappls.com/O2O/entity/place-details/{eLoc}
       -> name, address, locality, city, state, pincode, ...
  GET  https://atlas.mappls.com/api/places/textsearch/json?query=...
  GET  https://atlas.mappls.com/api/places/nearby/json?keywords=...&refLocation=lat,lng

Two field-availability facts worth knowing before you promise a client a
complete dataset:

  * addressTokens (which carries pincode) is documented as a RESTRICTED
    response field - it is not in the generic response for every account.
  * contact fields (mobileNo, landlineNo, email) are likewise entitlement
    gated on the Nearby/Text Search APIs.

So on a standard key you should expect name/address/lat/long reliably,
pincode usually via Place Details, and phone often not at all. The verifier
reports that as MISSING ON MAPPLS rather than as a mismatch, which is the
honest reading. If you need phone at scale, ask Mappls to enable those fields
on your project - that is a commercial conversation, not a code problem.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from .http_client import HttpClient
from .models import Listing


@dataclass
class Endpoints:
    token: str = "https://outpost.mappls.com/api/security/oauth/token"
    place_details: str = "https://place.mappls.com/O2O/entity/place-details/{eloc}"
    text_search: str = "https://atlas.mappls.com/api/places/textsearch/json"
    nearby: str = "https://atlas.mappls.com/api/places/nearby/json"


class MapplsApiError(RuntimeError):
    pass


class MapplsApiClient:
    """OAuth2 client-credentials client with token reuse."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        http: Optional[HttpClient] = None,
        endpoints: Optional[Endpoints] = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("MAPPLS_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MAPPLS_CLIENT_SECRET")
        self.http = http or HttpClient()
        self.endpoints = endpoints or Endpoints()
        self._token: Optional[str] = None
        self._token_type: str = "Bearer"
        self._token_expires_at: float = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # ---------------------------------------------------------------- auth

    def _fetch_token(self) -> None:
        if not self.configured:
            raise MapplsApiError(
                "MAPPLS_CLIENT_ID / MAPPLS_CLIENT_SECRET are not set. Create a "
                "project at https://apis.mappls.com/console/ and export them."
            )
        result = self.http.request(
            self.endpoints.token,
            method="POST",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            use_cache=False,
        )
        if not result.ok:
            raise MapplsApiError(f"token request failed: HTTP {result.status} {result.text[:200]}")
        try:
            payload = json.loads(result.text)
        except ValueError as exc:
            raise MapplsApiError(f"token response was not JSON: {result.text[:200]}") from exc
        self._token = payload.get("access_token")
        self._token_type = payload.get("token_type", "Bearer").title()
        # Refresh a minute early rather than discovering expiry mid-run.
        self._token_expires_at = time.time() + float(payload.get("expires_in", 3600)) - 60
        if not self._token:
            raise MapplsApiError(f"no access_token in token response: {result.text[:200]}")

    def _auth_header(self) -> Dict[str, str]:
        if not self._token or time.time() >= self._token_expires_at:
            self._fetch_token()
        return {"Authorization": f"{self._token_type} {self._token}"}

    # ----------------------------------------------------------- requests

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None, retry_auth: bool = True) -> Any:
        full = f"{url}?{urlencode({k: v for k, v in (params or {}).items() if v not in (None, '')})}" if params else url
        result = self.http.get(full, headers=self._auth_header())

        if result.status == 401 and retry_auth:
            self._token = None
            return self._get_json(url, params, retry_auth=False)
        if result.status == 403:
            raise MapplsApiError(
                f"HTTP 403 for {full} - either the rate limit was hit or your project is not "
                "entitled to this API/these response fields."
            )
        if result.status == 204:
            return None
        if not result.ok:
            raise MapplsApiError(f"HTTP {result.status} for {full}: {result.text[:200]}")
        try:
            return json.loads(result.text)
        except ValueError as exc:
            raise MapplsApiError(f"non-JSON response from {full}: {result.text[:200]}") from exc

    # ------------------------------------------------------------ methods

    def place_details(self, eloc: str) -> Any:
        return self._get_json(self.endpoints.place_details.format(eloc=eloc))

    def text_search(self, query: str, location: Optional[str] = None, filter_expr: Optional[str] = None, page: Optional[int] = None) -> Any:
        return self._get_json(
            self.endpoints.text_search,
            {"query": query, "location": location, "filter": filter_expr, "page": page},
        )

    def nearby(
        self,
        keywords: str,
        ref_location: str,
        page: int = 1,
        radius: Optional[int] = None,
        filter_expr: Optional[str] = None,
        sort_by: Optional[str] = None,
    ) -> Any:
        """
        Category search around a point. `ref_location` is "lat,lng" or an eLoc,
        radius is metres (max 10000). Use `page` to walk pageInfo.totalPages.
        """
        return self._get_json(
            self.endpoints.nearby,
            {
                "keywords": keywords,
                "refLocation": ref_location,
                "page": page,
                "radius": radius,
                "filter": filter_expr,
                "sortBy": sort_by,
            },
        )

    def listing_for_eloc(self, eloc: str, source_url: str) -> Listing:
        """
        Best-effort single listing for an eLoc.

        Place Details is the authority for name/address/pincode. It does not
        always carry coordinates, so we fall back to a Text Search on the eLoc
        (which does return latitude/longitude) to complete the record.
        """
        from .extract import extract_listing_from_json  # local import: avoids a cycle

        listing = Listing(source_url=source_url, eloc=eloc)
        details = self.place_details(eloc)
        if details:
            extract_listing_from_json(details, source_url, "mappls-api:place-details", listing)

        if listing.latitude is None or listing.longitude is None:
            try:
                search = self.text_search(eloc)
            except MapplsApiError:
                search = None
            if search:
                extract_listing_from_json(search, source_url, "mappls-api:text-search", listing)
        return listing
