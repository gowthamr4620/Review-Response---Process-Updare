"""
Command line entry point.

    # 1. Scrape a list of listing links
    python -m mapmyindia_scraper.cli scrape --urls links.txt --output scraped.xlsx

    # 2. Scrape AND cross-verify against the client's sheet (the main job)
    python -m mapmyindia_scraper.cli verify --input stores.xlsx --output report.xlsx

    # 3. Discover listings by category around a point (official API only)
    export MAPPLS_CLIENT_ID=... MAPPLS_CLIENT_SECRET=...
    python -m mapmyindia_scraper.cli nearby --keywords "jewellery store" \
        --location 28.6139,77.2090 --radius 10000 --pages 5 --output listings.xlsx

The input sheet for `verify` needs a column holding the Mappls link plus
whichever of the five fields you want checked; the column names are sniffed,
and the mapping it settled on is printed before anything is fetched. Check
that line before you trust the report.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .api import MapplsApiClient, MapplsApiError
from .excel_io import (
    describe_mapping,
    load_column_map,
    read_input_rows,
    write_scraped_workbook,
    write_verification_report,
)
from .extract import extract_listing_from_json
from .http_client import HttpClient
from .models import Listing, RowComparison
from .scraper import ListingScraper, load_urls_from_file
from .verify import VerifyConfig, verify_listing


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output", "-o", required=True, help="output .xlsx path")
    parser.add_argument("--rate", type=float, default=1.0, help="max requests per second (default 1.0)")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--cache-dir", default=".mappls_cache", help="response cache; '' disables it")
    parser.add_argument("--raw-dir", default=None, help="save each raw response here (debugging extraction)")
    parser.add_argument("--browser", action="store_true", help="render JS pages with Playwright when a plain fetch comes back empty")
    parser.add_argument("--no-api", action="store_true", help="skip the official Mappls API even if credentials are set")
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="fetch paths robots.txt disallows. Your call, your liability - see README.",
    )
    parser.add_argument("--limit", type=int, default=None, help="stop after N listings (useful for a dry run)")
    parser.add_argument("--quiet", action="store_true")


def _build_scraper(args: argparse.Namespace) -> ListingScraper:
    http = HttpClient(
        rate_per_sec=args.rate,
        timeout=args.timeout,
        retries=args.retries,
        cache_dir=args.cache_dir or None,
        respect_robots=not args.ignore_robots,
    )
    return ListingScraper(
        http=http,
        api=MapplsApiClient(http=http),
        use_api=not args.no_api,
        use_browser=args.browser,
        raw_dir=args.raw_dir,
        verbose=not args.quiet,
    )


def _warn_if_no_credentials(args: argparse.Namespace) -> None:
    if args.no_api:
        return
    if not (os.environ.get("MAPPLS_CLIENT_ID") and os.environ.get("MAPPLS_CLIENT_SECRET")):
        print(
            "note: MAPPLS_CLIENT_ID / MAPPLS_CLIENT_SECRET are not set, so the official "
            "API is unavailable and every listing falls back to page parsing. That is "
            "slower, less complete (phone and pincode are often absent from the markup) "
            "and it is the path Mappls' terms of use restrict. Get free credentials at "
            "https://apis.mappls.com/console/.",
            file=sys.stderr,
        )


# ----------------------------------------------------------------- commands

def command_scrape(args: argparse.Namespace) -> int:
    _warn_if_no_credentials(args)
    urls: List[str] = []
    if args.urls:
        urls = load_urls_from_file(args.urls)
    if args.input:
        rows, mapping, header_index = read_input_rows(args.input, args.sheet, load_column_map(args.column_map))
        print(f"input columns: {describe_mapping(mapping, header_index)}")
        urls += [r.url for r in rows if r.url]
    if args.url:
        urls += args.url
    if not urls:
        print("no URLs found - pass --urls, --url or --input", file=sys.stderr)
        return 2
    if args.limit:
        urls = urls[: args.limit]

    listings = list(_build_scraper(args).scrape_many(urls))
    write_scraped_workbook(listings, args.output)
    failed = sum(1 for l in listings if l.error)
    print(f"\nwrote {args.output}: {len(listings)} listings, {failed} with errors")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    _warn_if_no_credentials(args)
    rows, mapping, header_index = read_input_rows(args.input, args.sheet, load_column_map(args.column_map))
    print(f"input columns: {describe_mapping(mapping, header_index)}")
    if "url" not in mapping:
        print(
            "error: no listing-link column was recognised. Name it 'Mappls URL' (or "
            "'Link'), or point at it explicitly: --column-map '{\"url\": 3}' (0-based).",
            file=sys.stderr,
        )
        return 2
    rows = [r for r in rows if r.url]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("no rows with a listing link", file=sys.stderr)
        return 2

    config = VerifyConfig(
        name_match=args.name_threshold,
        address_match=args.address_threshold,
        geo_tolerance_m=args.geo_tolerance,
        geo_review_m=args.geo_review,
    )
    scraper = _build_scraper(args)

    comparisons: List[RowComparison] = []
    for index, row in enumerate(rows, start=1):
        if not args.quiet:
            print(f"[{index}/{len(rows)}] row {row.row_number}: {row.url}")
        listing = scraper.scrape(row.url)
        comparison = verify_listing(row.row_number, row.expected, listing, config)
        comparisons.append(comparison)
        if not args.quiet:
            detail = listing.error or " ".join(
                f"{name}={c.verdict.value}" for name, c in comparison.comparisons.items()
                if name != "longitude"
            )
            print(f"    -> {comparison.row_verdict}: {detail}")

    write_verification_report(
        comparisons,
        args.output,
        run_meta={
            "input file": args.input,
            "columns detected": describe_mapping(mapping, header_index),
            "name match threshold": config.name_match,
            "address match threshold": config.address_match,
            "geo tolerance (m)": config.geo_tolerance_m,
            "official API used": (not args.no_api) and bool(os.environ.get("MAPPLS_CLIENT_ID")),
            "browser rendering": args.browser,
            "robots.txt respected": not args.ignore_robots,
        },
    )

    totals = {}
    for comparison in comparisons:
        totals[comparison.row_verdict] = totals.get(comparison.row_verdict, 0) + 1
    print(f"\nwrote {args.output}")
    for verdict, count in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {verdict:12} {count}")
    return 0


def command_nearby(args: argparse.Namespace) -> int:
    """Category discovery around a point. Official API only, by design."""
    http = HttpClient(rate_per_sec=args.rate, timeout=args.timeout, retries=args.retries,
                      cache_dir=args.cache_dir or None)
    client = MapplsApiClient(http=http)
    if not client.configured:
        print("nearby needs MAPPLS_CLIENT_ID / MAPPLS_CLIENT_SECRET", file=sys.stderr)
        return 2

    listings: List[Listing] = []
    for page in range(1, args.pages + 1):
        try:
            payload = client.nearby(args.keywords, args.location, page=page, radius=args.radius)
        except MapplsApiError as exc:
            print(f"page {page}: {exc}", file=sys.stderr)
            break
        results = (payload or {}).get("suggestedLocations") or (payload or {}).get("results") or []
        if not results:
            break
        for item in results:
            listing = extract_listing_from_json(item, f"nearby:{args.keywords}@{args.location}", "mappls-api:nearby")
            listings.append(listing)
        print(f"page {page}: {len(results)} results (running total {len(listings)})")
        if args.limit and len(listings) >= args.limit:
            listings = listings[: args.limit]
            break

    write_scraped_workbook(listings, args.output)
    print(f"wrote {args.output}: {len(listings)} listings")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mapmyindia_scraper",
        description="Scrape Mappls (MapmyIndia) business listings and cross-verify them against a spreadsheet.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scrape = subparsers.add_parser("scrape", help="extract fields from listing links")
    scrape.add_argument("--urls", help="text file with one listing URL per line")
    scrape.add_argument("--url", action="append", help="a single listing URL (repeatable)")
    scrape.add_argument("--input", help="spreadsheet whose link column supplies the URLs")
    scrape.add_argument("--sheet", default=None)
    scrape.add_argument("--column-map", default=None)
    _add_common_arguments(scrape)
    scrape.set_defaults(func=command_scrape)

    verify = subparsers.add_parser("verify", help="scrape listing links and compare against the shared sheet")
    verify.add_argument("--input", required=True, help="client spreadsheet (.xlsx or .csv)")
    verify.add_argument("--sheet", default=None)
    verify.add_argument("--column-map", default=None, help='override detection, e.g. \'{"url": 3, "phone": 7}\' (0-based)')
    verify.add_argument("--name-threshold", type=float, default=0.88)
    verify.add_argument("--address-threshold", type=float, default=0.85)
    verify.add_argument("--geo-tolerance", type=float, default=100.0, help="metres within which coordinates count as a match")
    verify.add_argument("--geo-review", type=float, default=500.0, help="metres beyond which coordinates are a mismatch, not a review")
    _add_common_arguments(verify)
    verify.set_defaults(func=command_verify)

    nearby = subparsers.add_parser("nearby", help="discover listings by category near a point (official API)")
    nearby.add_argument("--keywords", required=True, help='category or brand, e.g. "coffee shop"')
    nearby.add_argument("--location", required=True, help='"lat,lng" or an eLoc')
    nearby.add_argument("--radius", type=int, default=5000, help="metres, max 10000")
    nearby.add_argument("--pages", type=int, default=3)
    _add_common_arguments(nearby)
    nearby.set_defaults(func=command_nearby)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
