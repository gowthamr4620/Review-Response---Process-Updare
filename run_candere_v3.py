import json
import os
import ssl
import sys
import time
import urllib.request

import pandas as pd
from build_prompt_v3 import build_prompt_locked_tone_v3

BUSINESS_NAME = "Candere Lifestyle Jewellery"
TONE = "Conversational"
RESPONSE_LENGTH = 80
SIGNATURE = "Candere Lifestyle Jewellery"

REVIEWS_PATH = "candere_reviews.xlsx"
OUTPUT_PATH = "output/candere_v3_output.xlsx"

API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = "claude-sonnet-4-6"


def _ssl_context():
    ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca_bundle and os.path.exists(ca_bundle):
        return ssl.create_default_context(cafile=ca_bundle)
    return None


def call_anthropic(prompt: str) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    ctx = _ssl_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        data = json.loads(resp.read())
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def main():
    df = pd.read_excel(REVIEWS_PATH)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

    results = []
    for i, row in df.iterrows():
        reviewer_name = str(row["ReviewerName"])
        rating = int(row["Rating"])
        review_text = str(row["Review"]) if pd.notna(row["Review"]) else ""

        prompt = build_prompt_locked_tone_v3(
            business_name=BUSINESS_NAME,
            reviewer_name=reviewer_name,
            rating=rating,
            review_text=review_text,
            response_length=RESPONSE_LENGTH,
            locked_tone=TONE,
            signature=SIGNATURE,
        )

        try:
            response_text = call_anthropic(prompt)
        except Exception as e:
            response_text = f"ERROR: {e}"

        results.append({
            "ReviewId": row.get("ReviewId", f"candere_{i}"),
            "ReviewerName": reviewer_name,
            "Rating": rating,
            "Review": review_text,
            "Response": response_text,
        })

        status = "OK" if not response_text.startswith("ERROR") else "ERR"
        print(f"[{i+1}/{len(df)}] {status} - {reviewer_name}")
        time.sleep(0.3)

    df_out = pd.DataFrame(results)
    df_out.to_excel(OUTPUT_PATH, index=False, engine="openpyxl")
    print(f"\nDone. Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
