import pandas as pd
import json
import os
import ssl
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from build_prompt_corrected import build_prompt_locked_tone

BUSINESS_NAME = "Candere Lifestyle Jewellery"
TONE = "Conversational"
RESPONSE_LENGTH = 80
SIGNATURE = BUSINESS_NAME


def _ssl_context():
    ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca_bundle and os.path.exists(ca_bundle):
        return ssl.create_default_context(cafile=ca_bundle)
    return None


def call_anthropic(prompt, api_key, model="claude-sonnet-4-6"):
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


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY")
        sys.exit(1)

    df = pd.read_excel(os.path.join(os.path.dirname(__file__), "candere_reviews.xlsx"))
    print(f"Running {len(df)} Candere reviews using build_prompt_corrected (locked tone)...")

    results = []
    for i, row in df.iterrows():
        review_text = str(row["Review"]) if pd.notna(row["Review"]) else ""
        prompt = build_prompt_locked_tone(
            business_name=BUSINESS_NAME,
            reviewer_name=str(row["ReviewerName"]),
            rating=int(row["Rating"]),
            review_text=review_text,
            response_length=RESPONSE_LENGTH,
            locked_tone=TONE,
            signature=SIGNATURE,
        )
        try:
            response = call_anthropic(prompt, api_key)
        except Exception as e:
            response = f"ERROR: {e}"

        results.append({
            "review_id": row.get("ReviewId", i),
            "reviewer_name": row["ReviewerName"],
            "rating": row["Rating"],
            "review": review_text,
            "response": response,
        })
        print(f"[candere] {i+1}/{len(df)} done")
        time.sleep(0.3)

    os.makedirs(os.path.join(os.path.dirname(__file__), "output"), exist_ok=True)
    out_path = os.path.join(os.path.dirname(__file__), "output", "candere_corrected_output.xlsx")
    pd.DataFrame(results).to_excel(out_path, index=False, engine="openpyxl")
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
