# bing_maps_scraper

Scrapes what Bing / Bing Maps *publicly displays* for a listing, so it can be compared
against what was pushed to Bing via API.

Fields: business name, address, PIN code, phone (raw + digits-only), website (+domain),
latitude, longitude, working hours (raw + normalised JSON), plus `ypid`, URL type,
status and **per-field provenance** (`field_sources`).

## Run

```bash
pip install -r bing_maps_scraper/requirements.txt
export FIRECRAWL_API_KEY=fc-...          # same Firecrawl account as the MCP connector

# input: CSV/XLSX with a `url` column (extra columns such as store_id are carried through
# as in_<col>), or a .txt with one URL per line
python -m bing_maps_scraper scrape input.csv -o output/ --country IN

python -m bing_maps_scraper reparse input.csv -o output/   # offline, from cached pages
```

Outputs in `output/`: `listings.xlsx` (listings, status_summary, field_coverage),
`listings.csv`, `listings.jsonl`, and `raw_cache/` (every fetched page, so nothing
needs re-scraping to fix a parser).

Fetchers: `firecrawl` (default when the key is set; REST API, JS-rendered), `playwright`
(`pip install playwright`), `http` (plain GET; poor for JS-heavy Bing Maps).
`--llm-extract` asks Firecrawl for LLM extraction as a last-resort fallback (costs extra credits).

## Status values
`ok` name+address found · `partial` some fields · `blocked` captcha/bot-check ·
`failed` fetch error or nothing parseable.

## Read this before trusting the numbers
- **Selectors are unverified against live Bing.** This was built in a sandbox with Bing and
  Firecrawl blocked. The parsers are layered (JSON-LD → embedded JSON → card DOM → text →
  URL → LLM) and tested on synthetic fixtures only. First run: scrape ~20 URLs of each
  type, inspect `field_coverage`, then fix selectors in `parsers.py` and run `reparse`.
- **Latitude/longitude provenance matters.** `field_sources` says `jsonld`/`embedded`
  (real pin) vs `url_cp` (map *centre* from the URL, not necessarily the pin). Exclude
  `url_cp` rows from distance-accuracy checks.
- Phone/PIN are normalised minimally; do the comparison-side normalisation in your
  evaluation step, not here, so the scrape stays a faithful record.
- Respect Bing's terms and keep `--workers` modest; `blocked` rows mean you're being throttled.

Tests: `python -m pytest bing_maps_scraper/tests`
