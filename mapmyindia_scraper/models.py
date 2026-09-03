"""
Data models for the Mappls (MapmyIndia) listing scraper and the
cross-verification step.

Two objects matter here:

  Listing        - what we managed to extract for one listing URL, plus
                   provenance (which strategy produced each field) so a
                   surprising value can be traced back to its source.
  RowComparison  - one row of the client's Excel: the values they shared,
                   the values we scraped, and a per-field verdict.

Every extracted field is Optional on purpose. Mappls does not expose the
same fields to every consumer (phone numbers and address tokens including
pincode are restricted in the generic API response), so "we could not find
it" has to stay distinguishable from "it disagrees". Collapsing those two
into one state is the single easiest way to make a verification report lie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# The five fields the brief asks for, in report order. latitude/longitude are
# compared together (as a distance) but carried separately.
SCRAPED_FIELDS = (
    "business_name",
    "address",
    "pincode",
    "latitude",
    "longitude",
    "phone",
)


@dataclass
class Listing:
    """One Mappls business listing as extracted from a single source URL."""

    source_url: str
    eloc: Optional[str] = None
    business_name: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phones: List[str] = field(default_factory=list)

    # Provenance / debugging.
    field_sources: Dict[str, str] = field(default_factory=dict)
    strategies_tried: List[str] = field(default_factory=list)
    fetched_at: Optional[str] = None
    raw_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def phone(self) -> Optional[str]:
        """Primary phone. Extras stay in .phones and are reported separately."""
        return self.phones[0] if self.phones else None

    @property
    def has_any_data(self) -> bool:
        return any(
            getattr(self, name) not in (None, "", [])
            for name in ("business_name", "address", "pincode", "latitude", "longitude")
        ) or bool(self.phones)

    def missing_fields(self) -> List[str]:
        return [f for f in SCRAPED_FIELDS if self.get(f) in (None, "")]

    def get(self, name: str) -> Any:
        return self.phone if name == "phone" else getattr(self, name, None)

    def fill_from(self, other: "Listing", source: str) -> None:
        """
        Fill only the blanks from another Listing.

        Extraction runs as a chain (official API -> embedded JSON -> HTML) and
        earlier strategies are the more trustworthy ones, so a later strategy
        may complete a record but never overwrite it. That rule is what keeps
        a regex guess from silently replacing an API value.
        """
        for name in ("eloc", "business_name", "address", "pincode", "latitude", "longitude"):
            if getattr(self, name) in (None, "") and getattr(other, name) not in (None, ""):
                setattr(self, name, getattr(other, name))
                self.field_sources[name] = other.field_sources.get(name, source)
        for phone in other.phones:
            if phone not in self.phones:
                self.phones.append(phone)
                self.field_sources.setdefault("phone", other.field_sources.get("phone", source))

    def to_row(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "eloc": self.eloc,
            "business_name": self.business_name,
            "address": self.address,
            "pincode": self.pincode,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "phone": self.phone,
            "additional_phones": ", ".join(self.phones[1:]) if len(self.phones) > 1 else None,
            "field_sources": "; ".join(f"{k}={v}" for k, v in sorted(self.field_sources.items())),
            "fetched_at": self.fetched_at,
            "error": self.error,
        }


class Verdict(str, Enum):
    """Per-field outcome of the cross-verification."""

    MATCH = "MATCH"
    NEAR_MATCH = "NEAR MATCH"          # fuzzy score in the review band
    MISMATCH = "MISMATCH"
    MISSING_ON_MAPPLS = "MISSING ON MAPPLS"   # we scraped the page, field absent
    MISSING_IN_SHEET = "MISSING IN SHEET"     # client did not share a value
    NOT_COMPARED = "NOT COMPARED"             # neither side has a value


@dataclass
class FieldComparison:
    field_name: str
    expected: Any
    scraped: Any
    verdict: Verdict
    score: Optional[float] = None    # 0..1 for fuzzy fields, metres for geo
    note: Optional[str] = None


@dataclass
class RowComparison:
    row_number: int
    source_url: str
    listing: Listing
    comparisons: Dict[str, FieldComparison] = field(default_factory=dict)

    @property
    def fetch_failed(self) -> bool:
        return bool(self.listing.error)

    @property
    def row_verdict(self) -> str:
        if self.fetch_failed:
            return "FETCH ERROR"
        verdicts = {c.verdict for c in self.comparisons.values()}
        if Verdict.MISMATCH in verdicts:
            return "MISMATCH"
        if Verdict.NEAR_MATCH in verdicts:
            return "REVIEW"
        if Verdict.MISSING_ON_MAPPLS in verdicts or Verdict.MISSING_IN_SHEET in verdicts:
            return "INCOMPLETE"
        if Verdict.MATCH in verdicts:
            return "MATCH"
        return "NOT COMPARED"
