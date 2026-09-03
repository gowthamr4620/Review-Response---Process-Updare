"""
Normalisation and comparison primitives.

Cross-verification lives or dies here. "SBI Branch, M.G. Road" and
"State Bank of India Branch, MG Rd" are the same listing; a naive string
compare calls them a mismatch and buries the reviewer in false positives.
Equally, a normaliser that is too aggressive will call two genuinely
different branches equal. Everything below is deliberately conservative:
it only removes noise that carries no identifying information (punctuation,
case, legal suffixes, standard Indian address abbreviations) and leaves the
judgement call to a similarity score with an explicit threshold.

All functions are pure and stdlib-only, which makes them cheap to unit test
against the failure cases you actually hit in Indian address data.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Iterable, Optional, Sequence

# Legal-entity suffixes: present or absent at random across data sources,
# never the thing that distinguishes two listings.
_LEGAL_SUFFIXES = {
    "pvt", "private", "ltd", "limited", "llp", "inc", "incorporated", "corp",
    "corporation", "co", "company", "and", "&",
}

# Standard Indian postal/address abbreviations, expanded to a canonical form.
_ADDRESS_ABBREVIATIONS = {
    "rd": "road", "st": "street", "ave": "avenue", "ln": "lane", "hwy": "highway",
    "nr": "near", "opp": "opposite", "bldg": "building", "blk": "block",
    "sec": "sector", "flr": "floor", "fl": "floor", "gr": "ground",
    "grd": "ground", "no": "number", "nos": "number", "apt": "apartment",
    "apts": "apartment", "ext": "extension", "extn": "extension",
    "pl": "place", "plc": "place", "sq": "square", "cross": "cross",
    "ph": "phase", "mkt": "market", "jn": "junction", "jnc": "junction",
    "cmplx": "complex", "twr": "tower", "soc": "society", "socy": "society",
    "dist": "district", "distt": "district", "po": "post office",
    "ps": "police station", "vill": "village", "twp": "township",
    "hno": "house number", "shp": "shop", "gali": "gali", "marg": "marg",
    "nagar": "nagar", "e": "east", "w": "west", "n": "north", "s": "south",
    "indl": "industrial", "estt": "estate", "chs": "cooperative housing society",
}

# Tokens that label the next value rather than identify the place. "Shop No 5"
# and "Shop 5" are the same shop, so the label is noise for comparison.
_DROP_TOKENS = {"india", "number"}

_PINCODE_RE = re.compile(r"\b([1-9]\d{5})\b")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def squash(text: Optional[str]) -> str:
    """Lowercase, de-accent, drop punctuation, collapse whitespace."""
    if not text:
        return ""
    out = _strip_accents(str(text)).lower()
    out = out.replace("&", " and ")
    out = _NON_ALNUM_RE.sub(" ", out)
    return _WS_RE.sub(" ", out).strip()


def _collapse_initials(tokens: list) -> list:
    """
    Join runs of single letters into one token: "m g road" -> "mg road".

    Indian addresses and business names are full of initials (M.G. Road,
    K.R. Puram, S.V. Road) written with dots, without dots, or run together.
    Without this, the same address spelled two ways scores as two addresses.
    """
    out, run = [], []
    for token in tokens:
        if len(token) == 1 and token.isalpha():
            run.append(token)
            continue
        if run:
            out.append("".join(run))
            run = []
        out.append(token)
    if run:
        out.append("".join(run))
    return out


def normalize_name(name: Optional[str]) -> str:
    """Canonical business name for comparison (never for display)."""
    tokens = [t for t in squash(name).split() if t not in _LEGAL_SUFFIXES]
    return " ".join(_collapse_initials(tokens))


def normalize_address(address: Optional[str], drop_pincode: bool = True) -> str:
    """
    Canonical address for comparison.

    The pincode is dropped by default because it is verified as its own field;
    leaving it in double-counts a pincode mismatch as an address mismatch too.
    """
    text = squash(address)
    if drop_pincode:
        text = _PINCODE_RE.sub(" ", text)
    tokens = _collapse_initials(text.split())
    tokens = [_ADDRESS_ABBREVIATIONS.get(t, t) for t in tokens]
    tokens = [t for t in tokens if t not in _DROP_TOKENS]
    return _WS_RE.sub(" ", " ".join(tokens)).strip()


def normalize_pincode(value: object) -> Optional[str]:
    """Return a 6-digit Indian PIN code, or None. Handles 110001.0 from Excel."""
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if len(digits) == 6 and digits[0] != "0":
        return digits
    match = _PINCODE_RE.search(text)
    return match.group(1) if match else None


def normalize_phone(value: object) -> Optional[str]:
    """
    Canonical Indian phone number: the 10 significant digits.

    Handles +91, 0091, leading 0, spaces, hyphens and Excel's habit of turning
    a phone number into a float. Numbers that cannot be reduced to a plausible
    10-digit subscriber number are returned as their raw digits so the report
    can still show something rather than silently dropping data.
    """
    if value is None:
        return None
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    for prefix in ("0091", "91", "0"):
        if len(digits) > 10 and digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    if len(digits) == 10:
        return digits
    return digits[-10:] if len(digits) > 10 else digits


def phone_digits_match(a: Optional[str], b: Optional[str]) -> bool:
    na, nb = normalize_phone(a), normalize_phone(b)
    if not na or not nb:
        return False
    return na[-10:] == nb[-10:] if min(len(na), len(nb)) >= 10 else na == nb


def parse_coordinate(value: object) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def in_india_bbox(lat: Optional[float], lng: Optional[float]) -> bool:
    """Rough mainland+islands bounding box, used only as a sanity check."""
    if lat is None or lng is None:
        return False
    return 6.0 <= lat <= 37.5 and 68.0 <= lng <= 97.5


def haversine_metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _token_set_ratio(a: str, b: str) -> float:
    """Jaccard-style overlap - order-insensitive, robust to reordered addresses."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _sequence_ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def similarity(a: str, b: str) -> float:
    """
    0..1 similarity of two already-normalised strings.

    Takes the max of a character-level ratio (catches typos and spelling
    variants) and a token-set ratio (catches reordered address components).
    Either signal alone produces avoidable false mismatches on real data.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return max(_sequence_ratio(a, b), _token_set_ratio(a, b))


def is_subset_match(a: str, b: str) -> bool:
    """True when one normalised string's tokens are wholly inside the other.

    Common and legitimate: the sheet holds the short address, Mappls holds the
    long one (or vice versa)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return ta <= tb or tb <= ta


def first_non_empty(values: Iterable[object]) -> Optional[object]:
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def dedupe(values: Sequence[str]) -> list:
    seen, out = set(), []
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
