"""
Field extraction from a fetched listing page or API payload.

Mappls' web front-end is a JavaScript app: the useful data is not in the
rendered markup, it is in a JSON blob the page ships (JSON-LD, __NEXT_DATA__,
or a bootstrap state object) or in an XHR the page makes. So the extraction
order is deliberately JSON-first and markup-last:

    1. JSON-LD  (schema.org LocalBusiness/Place) - stable, standardised
    2. Embedded app state (__NEXT_DATA__, __INITIAL_STATE__, __NUXT__)
    3. tel: links and meta tags (og:*, geo.position, ICBM)
    4. Regex over visible text - last resort, guesses, marked as such

Each field records which strategy produced it (Listing.field_sources), so when
a value looks wrong you can tell "the API said so" from "a regex found six
digits in a paragraph". Strategy 4 is the one that goes stale silently; the
provenance column is how you catch that.

Nothing here does network I/O - it is pure parsing, which means the whole
chain is unit-testable against saved fixtures.
"""

from __future__ import annotations

import html as html_module
import json
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .models import Listing
from .normalize import dedupe, normalize_phone, normalize_pincode, parse_coordinate

# Key aliases seen across Mappls' own payloads (placeName/placeAddress/eLoc),
# schema.org (name/telephone/postalCode) and generic store-locator JSON.
FIELD_ALIASES: Dict[str, Tuple[str, ...]] = {
    "business_name": ("placename", "poiname", "poi", "businessname", "storename", "name", "title", "displayname"),
    "address": ("placeaddress", "formattedaddress", "fulladdress", "streetaddress", "addressline1", "address", "addr"),
    "pincode": ("pincode", "pin", "postalcode", "postcode", "zipcode", "zip"),
    "latitude": ("latitude", "lat", "y"),
    "longitude": ("longitude", "lng", "lon", "long", "x"),
    "phone": ("telephone", "phonenumber", "phone", "mobileno", "mobile", "landlineno", "landline", "contactnumber", "contactno", "contact", "tel"),
    "eloc": ("eloc", "elocid", "placeid", "mappls_eloc"),
}

_SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.IGNORECASE | re.DOTALL)
_TYPE_ATTR_RE = re.compile(r"""type\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_ID_ATTR_RE = re.compile(r"""id\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_STATE_ASSIGN_RE = re.compile(
    r"(?:window\.)?(__INITIAL_STATE__|__NUXT__|__APP_STATE__|__PRELOADED_STATE__|__DATA__)\s*=\s*",
)
_TEL_HREF_RE = re.compile(r"""href\s*=\s*["']tel:([^"']+)["']""", re.IGNORECASE)
_META_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_ATTR_RE = re.compile(r"""(\w[\w:.-]*)\s*=\s*["']([^"']*)["']""")
_TAG_RE = re.compile(r"<(script|style)\b.*?</\1>|<[^>]+>", re.IGNORECASE | re.DOTALL)

# Indian mobile: 10 digits starting 6-9, optionally +91 prefixed.
_MOBILE_RE = re.compile(r"(?:\+?91[\s\-.]?)?\b([6-9]\d{9})\b")
# Indian landline: STD code (2-5 digits incl. leading 0) + 6-8 digit number.
_LANDLINE_RE = re.compile(r"\b(0\d{2,4}[\s\-.]?\d{6,8})\b")
_PINCODE_TEXT_RE = re.compile(r"\b([1-9]\d{5})\b")


# --------------------------------------------------------------------- JSON

def _balanced_json(text: str, start: int) -> Optional[str]:
    """Slice a complete {...} or [...] beginning at `start`, respecting strings."""
    if start >= len(text) or text[start] not in "{[":
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def iter_embedded_json(html: str) -> Iterator[Tuple[str, Any]]:
    """Yield (source_label, parsed_json) for every JSON blob shipped in the page."""
    for attrs, body in _SCRIPT_RE.findall(html):
        script_type = (_TYPE_ATTR_RE.search(attrs) or [None, ""])[1].lower()
        script_id = (_ID_ATTR_RE.search(attrs) or [None, ""])[1]
        body = body.strip()
        if not body:
            continue

        if "ld+json" in script_type:
            for chunk in _json_candidates(body):
                yield "json-ld", chunk
            continue

        if script_id in ("__NEXT_DATA__", "__NUXT_DATA__") or "application/json" in script_type:
            for chunk in _json_candidates(body):
                yield f"embedded-json:{script_id or 'application/json'}", chunk
            continue

        match = _STATE_ASSIGN_RE.search(body)
        if match:
            blob = _balanced_json(body, match.end())
            if blob:
                try:
                    yield f"embedded-json:{match.group(1)}", json.loads(blob)
                except ValueError:
                    pass


def _json_candidates(body: str) -> Iterator[Any]:
    try:
        yield json.loads(body)
        return
    except ValueError:
        pass
    # Some pages emit several JSON-LD objects back to back, or wrap them in
    # comments/CDATA. Recover whatever parses rather than dropping the block.
    index = 0
    while index < len(body):
        if body[index] in "{[":
            blob = _balanced_json(body, index)
            if blob:
                try:
                    yield json.loads(blob)
                except ValueError:
                    pass
                index += len(blob)
                continue
        index += 1


def walk_json(node: Any, path: str = "") -> Iterator[Tuple[str, str, Any]]:
    """Depth-first walk yielding (path, key, value) for every scalar-bearing key."""
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, str(key), value
            yield from walk_json(value, child_path)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            child_path = f"{path}[{i}]"
            yield from walk_json(value, child_path)


def _scalar(value: Any) -> Optional[str]:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    if isinstance(value, list) and value:
        return _scalar(value[0])
    return None


def extract_fields_from_json(payload: Any) -> Dict[str, Any]:
    """
    Pull our six fields out of an arbitrary JSON payload by key alias.

    The first match for each alias wins, and aliases are ordered most-specific
    first ("placeName" before "name") so a page-level title does not beat the
    listing's own name.
    """
    found: Dict[str, Any] = {}
    phones: List[str] = []
    ranked: Dict[str, int] = {}

    for _path, key, value in walk_json(payload):
        key_lower = key.lower().replace("_", "").replace("-", "")
        for field_name, aliases in FIELD_ALIASES.items():
            if key_lower not in aliases:
                continue
            rank = aliases.index(key_lower)
            text = _scalar(value)
            if text is None:
                continue
            if field_name == "phone":
                phones.extend(_split_phones(text))
                continue
            if field_name in found and ranked.get(field_name, 99) <= rank:
                continue
            found[field_name] = text
            ranked[field_name] = rank

    if phones:
        found["phones"] = dedupe([p for p in (normalize_phone(p) for p in phones) if p])
    return found


def _split_phones(text: str) -> List[str]:
    return [p for p in re.split(r"[,;/|]| or ", str(text)) if any(c.isdigit() for c in p)]


# ------------------------------------------------------------------ JSON-LD

_LOCAL_BUSINESS_TYPES = {
    "localbusiness", "place", "organization", "restaurant", "bank", "hotel",
    "financialservice", "automotivebusiness", "professionalservice", "store",
}
# schema.org has ~100 LocalBusiness subtypes (JewelryStore, BankOrCreditUnion,
# GasStation ...). Enumerating them is a losing game, so match on the suffix
# too, and fall back to shape: a node with a name plus an address or geo block
# is a place whatever it calls itself.
_BUSINESS_TYPE_SUFFIXES = ("store", "shop", "business", "service", "agency", "clinic", "market")


def _looks_like_a_place(node: dict) -> bool:
    types = node.get("@type")
    types = [types] if isinstance(types, str) else (types or [])
    for raw in types:
        name = str(raw).lower()
        if name in _LOCAL_BUSINESS_TYPES or name.endswith(_BUSINESS_TYPE_SUFFIXES):
            return True
    return bool(node.get("name")) and bool(node.get("address") or node.get("geo"))


def iter_jsonld_places(node: Any) -> Iterator[dict]:
    """Yield schema.org nodes that describe a place/business, @graph included."""
    if isinstance(node, list):
        for item in node:
            yield from iter_jsonld_places(item)
        return
    if not isinstance(node, dict):
        return
    if "@graph" in node:
        yield from iter_jsonld_places(node["@graph"])
    if _looks_like_a_place(node):
        yield node
    for value in node.values():
        if isinstance(value, (dict, list)):
            yield from iter_jsonld_places(value)


def extract_fields_from_jsonld(node: dict) -> Dict[str, Any]:
    address = node.get("address")
    out: Dict[str, Any] = {}
    if isinstance(address, dict):
        parts = [
            address.get("streetAddress"),
            address.get("addressLocality"),
            address.get("addressRegion"),
        ]
        joined = ", ".join(str(p) for p in parts if p)
        if joined:
            out["address"] = joined
        if address.get("postalCode"):
            out["pincode"] = str(address["postalCode"])
    elif isinstance(address, str) and address.strip():
        out["address"] = address.strip()

    geo = node.get("geo")
    if isinstance(geo, dict):
        out["latitude"] = geo.get("latitude")
        out["longitude"] = geo.get("longitude")

    if node.get("name"):
        out["business_name"] = str(node["name"]).strip()
    telephone = node.get("telephone")
    if telephone:
        phones = _split_phones(telephone if isinstance(telephone, str) else str(telephone))
        out["phones"] = dedupe([p for p in (normalize_phone(x) for x in phones) if p])
    return {k: v for k, v in out.items() if v not in (None, "", [])}


# --------------------------------------------------------------- HTML bits

def strip_tags(html: str) -> str:
    return html_module.unescape(_TAG_RE.sub(" ", html))


def extract_meta_fields(html: str) -> Dict[str, Any]:
    """og:*, place:location:*, geo.position and ICBM meta tags."""
    out: Dict[str, Any] = {}
    for tag in _META_RE.findall(html):
        attrs = {k.lower(): v for k, v in _META_ATTR_RE.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        content = (attrs.get("content") or "").strip()
        if not key or not content:
            continue
        if key in ("og:title", "twitter:title") and "business_name" not in out:
            out["business_name"] = content
        elif key in ("place:location:latitude", "og:latitude", "geo.latitude"):
            out["latitude"] = content
        elif key in ("place:location:longitude", "og:longitude", "geo.longitude"):
            out["longitude"] = content
        elif key in ("geo.position", "icbm"):
            bits = re.split(r"[;,]", content)
            if len(bits) == 2:
                out.setdefault("latitude", bits[0].strip())
                out.setdefault("longitude", bits[1].strip())
        elif key == "og:street-address":
            out.setdefault("address", content)
        elif key == "og:postal-code":
            out.setdefault("pincode", content)
        elif key == "og:phone_number":
            out.setdefault("phones", dedupe([p for p in (normalize_phone(x) for x in _split_phones(content)) if p]))
    return out


def extract_text_hints(html: str) -> Dict[str, Any]:
    """Regex guesses over visible text. Lowest confidence in the chain."""
    text = strip_tags(html)
    out: Dict[str, Any] = {}
    pincodes = _PINCODE_TEXT_RE.findall(text)
    if pincodes:
        # A page can mention several 6-digit numbers; the most repeated one is
        # the likeliest actual pincode of the listing.
        out["pincode"] = max(set(pincodes), key=pincodes.count)
    phones = _MOBILE_RE.findall(text) + [m for m in _LANDLINE_RE.findall(text)]
    normalised = dedupe([p for p in (normalize_phone(x) for x in phones) if p])
    if normalised:
        out["phones"] = normalised[:3]
    return out


def extract_tel_links(html: str) -> Dict[str, Any]:
    phones = dedupe([p for p in (normalize_phone(x) for x in _TEL_HREF_RE.findall(html)) if p])
    return {"phones": phones} if phones else {}


# ------------------------------------------------------------------ chain

def _apply(listing: Listing, fields: Dict[str, Any], source: str) -> None:
    """Fill blanks on `listing` from `fields`, recording provenance."""
    for name in ("eloc", "business_name", "address"):
        value = fields.get(name)
        if value and not getattr(listing, name):
            setattr(listing, name, str(value).strip())
            listing.field_sources[name] = source

    pincode = normalize_pincode(fields.get("pincode"))
    if pincode and not listing.pincode:
        listing.pincode = pincode
        listing.field_sources["pincode"] = source

    for name in ("latitude", "longitude"):
        value = parse_coordinate(fields.get(name))
        if value is not None and getattr(listing, name) is None:
            setattr(listing, name, value)
            listing.field_sources[name] = source

    for phone in fields.get("phones") or []:
        if phone and phone not in listing.phones:
            listing.phones.append(phone)
            listing.field_sources.setdefault("phone", source)


def extract_listing_from_html(html: str, source_url: str, listing: Optional[Listing] = None) -> Listing:
    """Run the full JSON-first extraction chain over one HTML document."""
    listing = listing or Listing(source_url=source_url)

    for label, payload in iter_embedded_json(html):
        if label == "json-ld":
            for place in iter_jsonld_places(payload):
                _apply(listing, extract_fields_from_jsonld(place), "json-ld")
                listing.strategies_tried.append("json-ld")
        else:
            _apply(listing, extract_fields_from_json(payload), label)
            listing.strategies_tried.append(label)

    _apply(listing, extract_tel_links(html), "tel-link")
    _apply(listing, extract_meta_fields(html), "meta-tag")
    _apply(listing, extract_text_hints(html), "text-regex")
    listing.strategies_tried.extend(["tel-link", "meta-tag", "text-regex"])

    # An address that carries its pincode still counts as a pincode source.
    if not listing.pincode and listing.address:
        listing.pincode = normalize_pincode(listing.address)
        if listing.pincode:
            listing.field_sources["pincode"] = "address"
    return listing


def extract_listing_from_json(payload: Any, source_url: str, source: str, listing: Optional[Listing] = None) -> Listing:
    """Same chain for a JSON API response (official API or an XHR payload)."""
    listing = listing or Listing(source_url=source_url)
    for place in iter_jsonld_places(payload):
        _apply(listing, extract_fields_from_jsonld(place), f"{source}:json-ld")
    _apply(listing, extract_fields_from_json(payload), source)
    listing.strategies_tried.append(source)
    if not listing.pincode and listing.address:
        listing.pincode = normalize_pincode(listing.address)
        if listing.pincode:
            listing.field_sources["pincode"] = "address"
    return listing
