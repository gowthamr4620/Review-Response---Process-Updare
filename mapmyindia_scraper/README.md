# Mappls (MapmyIndia) listing scraper + cross-verifier

Takes a list of Mappls listing links, pulls out the five fields you asked for
— **business name, address, PIN code, latitude/longitude, phone number** —
and checks each one against the values shared in a spreadsheet. Output is a
colour-coded Excel report: what the sheet says, what Mappls says, and a
verdict per field.

```
pip install -r mapmyindia_scraper/requirements.txt

# the main job: scrape the links in the sheet and verify every field
python -m mapmyindia_scraper.cli verify --input stores.xlsx --output report.xlsx

# just extract, no comparison
python -m mapmyindia_scraper.cli scrape --urls links.txt --output scraped.xlsx

# discover listings by category near a point (official API only)
python -m mapmyindia_scraper.cli nearby --keywords "jewellery store" \
    --location 28.6139,77.2090 --radius 10000 --pages 5 --output listings.xlsx
```

## Read this before you run it at scale

**Use the official API.** Mappls' terms of use prohibit scraping their web
properties. The sanctioned route is their REST API, which has a free tier:

```
# https://apis.mappls.com/console/  -> create a project -> copy the credentials
export MAPPLS_CLIENT_ID=...
export MAPPLS_CLIENT_SECRET=...
```

With credentials set, any link that yields an eLoc (Mappls' 6-character
digital address, e.g. `https://mappls.com/2ozc1r`) is resolved through the
Place Details API and the page is never fetched. That path is faster, more
complete, doesn't break on a redesign, and doesn't put you on the wrong side
of an agreement. HTML parsing exists for links the API can't resolve —
brand-hosted store-locator pages, mostly — not as a way around getting a key.

**Two fields are not guaranteed, whichever route you take.** Mappls documents
`addressTokens` (which carries the pincode) and the contact fields
(`mobileNo`, `landlineNo`, `email`) as *restricted* response fields, gated on
your project's entitlement. On a standard key expect name, address and
coordinates reliably; pincode usually via Place Details; phone often not at
all. If phone at scale is the requirement, that's a commercial conversation
with Mappls, not something more code can fix. The report says
`MISSING ON MAPPLS` for these rather than pretending it found a mismatch.

## The input sheet

One column must hold the listing link. Any of the five value columns you
include get verified; the rest are skipped. Column names are sniffed
(`Store Name`, `Full Address`, `PIN Code`, `Latitude`, `Longitude`,
`Contact Number`, `Mappls Link`, and the obvious variants), a banner row
above the header is fine, and the mapping it settled on is printed before
anything is fetched:

```
input columns: header row 2; business_name -> col A, address -> col B, ... url -> col G
```

**Check that line.** If it guessed wrong, correct it explicitly rather than
renaming your client's file:

```
python -m mapmyindia_scraper.cli verify --input stores.xlsx --output report.xlsx \
    --column-map '{"url": 6, "phone": 5}'      # 0-based column indexes
```

## Reading the report

`Verification` holds every row; `Needs Attention` repeats only the rows that
failed; `Summary` has per-field counts and the settings the run used.

| Verdict | Means |
|---|---|
| `MATCH` | Same value, allowing for formatting and abbreviation differences |
| `NEAR MATCH` | Close but not conclusive — a human should look |
| `MISMATCH` | Genuinely different values |
| `MISSING ON MAPPLS` | The listing doesn't publish this field |
| `MISSING IN SHEET` | The client didn't share a value |
| `NOT COMPARED` | Neither side has a value |

Row-level: `MATCH`, `REVIEW`, `INCOMPLETE`, `MISMATCH`, `FETCH ERROR`.

What the comparison does *not* do is a naive string equality check, because
that would bury you in false positives:

- **Names** ignore case, punctuation and legal suffixes: `Kalyan Jewellers
  Pvt. Ltd.` == `Kalyan Jewellers`.
- **Addresses** expand standard Indian abbreviations (`Gr Flr` → ground floor,
  `Opp` → opposite, `Blk` → block, `Pl` → place), collapse initials (`M.G.` ==
  `MG`), and treat a shortened address contained in the longer one as a match.
- **Coordinates** are compared as one distance in metres (default: ≤100 m is a
  match, ≤500 m goes to review), not as float equality. It also explicitly
  detects **swapped latitude/longitude** in the sheet — the most common
  coordinate error in Indian store data, and one that looks like a wild
  mismatch until someone spots it.
- **Phones** compare the significant 10 digits, so `+91 98765 43210` ==
  `09876543210`, and a match against a *secondary* number on the listing is
  reported as a match with a note.

Thresholds are arguments, and every verdict carries its score so you can see
how close a call was:

```
--name-threshold 0.88 --address-threshold 0.85 --geo-tolerance 100 --geo-review 500
```

## When extraction comes back empty

Mappls' front end is a JavaScript app, so a plain fetch can return a shell
with nothing in it. In order:

1. Set the API credentials. This is the fix, not a workaround.
2. `--browser` renders the page with Playwright first
   (`pip install playwright && playwright install chromium`). Costs ~2–4s per
   listing.
3. `--raw-dir raw/` saves every response. Open one, find where the fields
   actually live, and add the key names to `FIELD_ALIASES` in `extract.py` —
   the extractor matches by key alias across any JSON shape, so a new payload
   layout is usually a one-line change.

Every field records where it came from (the `Field Sources` column):
`json-ld`, `mappls-api:place-details`, `text-regex`, `url-hint`, and so on.
When a value looks wrong, that column tells you whether the API said so or a
regex guessed it. `text-regex` and `url-hint` are guesses by construction —
a pincode-shaped number found in prose, or the map's viewport centre rather
than the shop's own coordinates.

## Being a good citizen

Default rate limit is 1 request/second (`--rate`), responses are cached to
`.mappls_cache` so re-running a verification doesn't re-hit the site, and
`robots.txt` is honoured. `--ignore-robots` exists; using it is a decision you
should make deliberately, per site, and own.

## Tests

```
python -m unittest discover -s mapmyindia_scraper/tests -t .
```

35 tests, no network: the extraction chain runs against saved fixtures and the
full spreadsheet → scrape → verify → report pipeline runs against a faked HTTP
layer.
