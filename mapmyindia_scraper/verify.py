"""
Cross-verification: what the client shared vs what Mappls actually shows.

Design rules, in order of how much trouble they save:

1. Missing is not mismatch. If Mappls does not publish a phone number, that
   is MISSING ON MAPPLS. Calling it a mismatch invents a discrepancy and
   sends someone off to "fix" correct data.
2. Fuzzy fields get three bands, not two: MATCH / NEAR MATCH / MISMATCH.
   The middle band is where a human should look. Real address data will not
   survive a binary rule.
3. Coordinates are compared as one distance in metres, not two float equality
   checks. 28.6139 vs 28.61391 is the same shop.
4. Swapped latitude/longitude is checked explicitly, because in Indian data
   it is the single most common coordinate error and it looks like a wild
   mismatch until you spot it.

Thresholds are arguments, not constants, and every verdict carries its score
so a reviewer can see how close a call was.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .models import FieldComparison, Listing, RowComparison, Verdict
from .normalize import (
    haversine_metres,
    in_india_bbox,
    is_subset_match,
    normalize_address,
    normalize_name,
    normalize_phone,
    normalize_pincode,
    phone_digits_match,
    similarity,
)


@dataclass
class VerifyConfig:
    name_match: float = 0.88
    name_review: float = 0.65
    address_match: float = 0.85
    address_review: float = 0.60
    geo_tolerance_m: float = 100.0
    geo_review_m: float = 500.0


def _presence_verdict(expected: Any, scraped: Any) -> Optional[Verdict]:
    """Return a verdict when one side has nothing to compare, else None."""
    expected_empty = expected in (None, "", [])
    scraped_empty = scraped in (None, "", [])
    if expected_empty and scraped_empty:
        return Verdict.NOT_COMPARED
    if scraped_empty:
        return Verdict.MISSING_ON_MAPPLS
    if expected_empty:
        return Verdict.MISSING_IN_SHEET
    return None


def _fuzzy_comparison(
    field_name: str,
    expected: Any,
    scraped: Any,
    normalizer,
    match_threshold: float,
    review_threshold: float,
) -> FieldComparison:
    presence = _presence_verdict(expected, scraped)
    if presence:
        return FieldComparison(field_name, expected, scraped, presence)

    a, b = normalizer(expected), normalizer(scraped)
    score = similarity(a, b)
    note = None
    if score < match_threshold and is_subset_match(a, b):
        # One side is a shortened form of the other - legitimate, and common
        # when the sheet holds a trimmed address.
        score = max(score, match_threshold)
        note = "one value is contained in the other"

    if score >= match_threshold:
        verdict = Verdict.MATCH
    elif score >= review_threshold:
        verdict = Verdict.NEAR_MATCH
        note = note or "close, but not close enough to auto-accept"
    else:
        verdict = Verdict.MISMATCH
    return FieldComparison(field_name, expected, scraped, verdict, score, note)


def compare_pincode(expected: Any, scraped: Any) -> FieldComparison:
    expected_pin, scraped_pin = normalize_pincode(expected), normalize_pincode(scraped)
    presence = _presence_verdict(expected_pin, scraped_pin)
    if presence:
        return FieldComparison("pincode", expected_pin or expected, scraped_pin or scraped, presence)
    match = expected_pin == scraped_pin
    return FieldComparison(
        "pincode",
        expected_pin,
        scraped_pin,
        Verdict.MATCH if match else Verdict.MISMATCH,
        1.0 if match else 0.0,
    )


def compare_phone(expected: Any, scraped: Any, listing: Optional[Listing] = None) -> FieldComparison:
    expected_phone, scraped_phone = normalize_phone(expected), normalize_phone(scraped)
    presence = _presence_verdict(expected_phone, scraped_phone)
    if presence:
        return FieldComparison("phone", expected_phone or expected, scraped_phone or scraped, presence)

    if phone_digits_match(expected_phone, scraped_phone):
        return FieldComparison("phone", expected_phone, scraped_phone, Verdict.MATCH, 1.0)

    # A listing can carry several numbers; matching any of them is a match,
    # with a note so the reviewer knows it was not the primary one.
    for alternate in (listing.phones if listing else [])[1:]:
        if phone_digits_match(expected_phone, alternate):
            return FieldComparison(
                "phone", expected_phone, scraped_phone, Verdict.MATCH, 1.0,
                f"matched secondary number {alternate} listed on Mappls",
            )
    return FieldComparison("phone", expected_phone, scraped_phone, Verdict.MISMATCH, 0.0)


def compare_coordinates(
    expected_lat: Any,
    expected_lng: Any,
    scraped_lat: Any,
    scraped_lng: Any,
    config: VerifyConfig,
) -> Dict[str, FieldComparison]:
    """Compare a coordinate pair once, then report the result on both fields."""
    have_expected = expected_lat is not None and expected_lng is not None
    have_scraped = scraped_lat is not None and scraped_lng is not None

    if not have_expected or not have_scraped:
        verdict = (
            Verdict.NOT_COMPARED
            if not have_expected and not have_scraped
            else (Verdict.MISSING_ON_MAPPLS if not have_scraped else Verdict.MISSING_IN_SHEET)
        )
        return {
            "latitude": FieldComparison("latitude", expected_lat, scraped_lat, verdict),
            "longitude": FieldComparison("longitude", expected_lng, scraped_lng, verdict),
        }

    distance = haversine_metres(expected_lat, expected_lng, scraped_lat, scraped_lng)
    note = f"{distance:,.0f} m apart"

    if distance <= config.geo_tolerance_m:
        verdict = Verdict.MATCH
    elif distance <= config.geo_review_m:
        verdict = Verdict.NEAR_MATCH
    else:
        verdict = Verdict.MISMATCH
        swapped = haversine_metres(expected_lng, expected_lat, scraped_lat, scraped_lng)
        if swapped <= config.geo_tolerance_m:
            note = f"{note} - latitude and longitude look swapped in the sheet"
        elif not in_india_bbox(expected_lat, expected_lng):
            note = f"{note} - the sheet's coordinates fall outside India"

    return {
        "latitude": FieldComparison("latitude", expected_lat, scraped_lat, verdict, distance, note),
        "longitude": FieldComparison("longitude", expected_lng, scraped_lng, verdict, distance, note),
    }


def verify_listing(
    row_number: int,
    expected: Dict[str, Any],
    listing: Listing,
    config: Optional[VerifyConfig] = None,
) -> RowComparison:
    config = config or VerifyConfig()
    comparison = RowComparison(row_number=row_number, source_url=listing.source_url, listing=listing)

    if listing.error:
        # Nothing was scraped, so nothing can be verified; the row verdict
        # already says FETCH ERROR and the expected values are preserved.
        for name, value in expected.items():
            comparison.comparisons[name] = FieldComparison(name, value, None, Verdict.MISSING_ON_MAPPLS)
        return comparison

    comparison.comparisons["business_name"] = _fuzzy_comparison(
        "business_name", expected.get("business_name"), listing.business_name,
        normalize_name, config.name_match, config.name_review,
    )
    comparison.comparisons["address"] = _fuzzy_comparison(
        "address", expected.get("address"), listing.address,
        normalize_address, config.address_match, config.address_review,
    )
    comparison.comparisons["pincode"] = compare_pincode(expected.get("pincode"), listing.pincode)
    comparison.comparisons.update(
        compare_coordinates(
            expected.get("latitude"), expected.get("longitude"),
            listing.latitude, listing.longitude, config,
        )
    )
    comparison.comparisons["phone"] = compare_phone(expected.get("phone"), listing.phone, listing)
    return comparison
