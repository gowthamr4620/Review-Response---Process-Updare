"""
Runs the prompt builder across all configured clients' review files, calls
the LLM API for each review, and writes per-client output CSVs plus a
combined file for cross-client diagnostics.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    # or: export OPENAI_API_KEY=sk-...
    python scripts/run_batch.py --provider anthropic --sample 30
    python scripts/run_batch.py --provider openai --sample 30 --client candere

Notes:
- Reads review files expected to have columns: ReviewerName, Rating, Review
  (extra columns are ignored). If your export uses different column names,
  adjust COLUMN_MAP below rather than renaming your source files.
- --sample N takes a random sample of N reviews per client (for quick
  iteration). Omit --sample to run the full file.
- previous_responses (the anti-repetition memory feed) is populated
  progressively AS THIS SCRIPT RUNS, per client, so later reviews in the
  batch get earlier ones as "do not repeat this phrasing" context - same
  mechanism the production system should use in real time.
"""

import argparse
import csv
import os
import ssl
import sys
import time
import json
import random
import urllib.request


def _ssl_context():
    ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca_bundle and os.path.exists(ca_bundle):
        return ssl.create_default_context(cafile=ca_bundle)
    return None

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config"))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from build_prompt import build_review_prompt
from clients import CLIENTS

COLUMN_MAP = {
    "reviewer_name": "ReviewerName",
    "rating": "Rating",
    "review": "Review",
    "review_id": "ReviewId",  # optional; falls back to row index if absent
}

MAX_PREVIOUS_RESPONSES_IN_CONTEXT = 5


def call_anthropic(prompt: str, api_key: str, model: str = "claude-sonnet-4-6") -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def call_openai(prompt: str, api_key: str, model: str = "gpt-4o") -> str:
    body = json.dumps({
        "model": model,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()


def run_for_client(client_key: str, client_entry: dict, provider: str, api_key: str,
                    sample: int | None, model: str) -> list[dict]:
    config = client_entry["config"]
    reviews_path = client_entry["reviews_file"]

    if not os.path.exists(reviews_path):
        print(f"[{client_key}] SKIPPED - reviews file not found: {reviews_path}")
        return []

    df = pd.read_excel(reviews_path) if reviews_path.endswith((".xlsx", ".xls")) else pd.read_csv(reviews_path)

    missing_cols = [v for v in (COLUMN_MAP["reviewer_name"], COLUMN_MAP["rating"], COLUMN_MAP["review"])
                    if v not in df.columns]
    if missing_cols:
        print(f"[{client_key}] SKIPPED - missing expected columns: {missing_cols}. "
              f"Found columns: {list(df.columns)}. Adjust COLUMN_MAP if names differ.")
        return []

    if sample:
        df = df.sample(min(sample, len(df)), random_state=7).reset_index(drop=True)

    results = []
    previous_responses: list[str] = []

    for i, row in df.iterrows():
        review_id = str(row[COLUMN_MAP["review_id"]]) if COLUMN_MAP["review_id"] in df.columns else f"{client_key}_{i}"
        reviewer_name = str(row[COLUMN_MAP["reviewer_name"]])
        rating = int(row[COLUMN_MAP["rating"]])
        review_text = str(row[COLUMN_MAP["review"]]) if pd.notna(row[COLUMN_MAP["review"]]) else None

        prompt = build_review_prompt(
            config=config,
            reviewer_name=reviewer_name,
            rating=rating,
            review_text=review_text,
            review_id=review_id,
            previous_responses=previous_responses[-MAX_PREVIOUS_RESPONSES_IN_CONTEXT:] if previous_responses else None,
        )

        try:
            if provider == "anthropic":
                response_text = call_anthropic(prompt, api_key, model=model)
            else:
                response_text = call_openai(prompt, api_key, model=model)
        except Exception as e:
            response_text = f"ERROR: {e}"

        results.append({
            "client_id": client_key,
            "review_id": review_id,
            "reviewer_name": reviewer_name,
            "rating": rating,
            "review": review_text,
            "response": response_text,
        })

        if not response_text.startswith("ERROR"):
            previous_responses.append(response_text)

        print(f"[{client_key}] {i+1}/{len(df)} done")
        time.sleep(0.3)  # light throttle; adjust per your rate limits

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["anthropic", "openai"], required=True)
    parser.add_argument("--model", default=None, help="Override default model name")
    parser.add_argument("--sample", type=int, default=None, help="Sample N reviews per client")
    parser.add_argument("--client", default=None, help="Run only this client key (default: all)")
    args = parser.parse_args()

    if args.provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        model = args.model or "claude-sonnet-4-6"
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        model = args.model or "gpt-4o"

    if not api_key:
        print(f"ERROR: set the appropriate API key env var for provider '{args.provider}'.")
        sys.exit(1)

    os.makedirs(os.path.join(os.path.dirname(__file__), "..", "output"), exist_ok=True)

    clients_to_run = {args.client: CLIENTS[args.client]} if args.client else CLIENTS

    all_results = []
    for client_key, client_entry in clients_to_run.items():
        client_results = run_for_client(client_key, client_entry, args.provider, api_key, args.sample, model)
        if client_results:
            out_path = os.path.join(os.path.dirname(__file__), "..", "output", f"{client_key}_output.csv")
            pd.DataFrame(client_results).to_csv(out_path, index=False)
            print(f"[{client_key}] saved -> {out_path}")
        all_results.extend(client_results)

    if all_results:
        combined_path = os.path.join(os.path.dirname(__file__), "..", "output", "combined_output.csv")
        pd.DataFrame(all_results).to_csv(combined_path, index=False)
        print(f"Combined -> {combined_path}")


if __name__ == "__main__":
    main()
