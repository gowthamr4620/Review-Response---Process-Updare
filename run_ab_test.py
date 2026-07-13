import pandas as pd
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from build_prompt_corrected import build_prompt_locked_tone
from build_prompt_with_grounding import build_prompt_locked_tone_with_grounding

BUSINESS_NAME = "Candere Lifestyle Jewellery"
TONE = "Conversational"
RESPONSE_LENGTH = 80
SIGNATURE = BUSINESS_NAME  # per instruction: signature = business name


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
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def run_variant(df, builder_fn, variant_name, api_key):
    results = []
    for i, row in df.iterrows():
        review_text = str(row["Review"]) if pd.notna(row["Review"]) else ""
        prompt = builder_fn(
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
            "variant": variant_name,
            "review_id": row.get("ReviewId", i),
            "reviewer_name": row["ReviewerName"],
            "rating": row["Rating"],
            "review": review_text,
            "response": response,
        })
        print(f"[{variant_name}] {i+1}/{len(df)} done")
        time.sleep(0.3)
    return results


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: set ANTHROPIC_API_KEY")
        sys.exit(1)

    df = pd.read_excel("/mnt/user-data/uploads/google_review_responses_Candere_top100_345star__1_.xlsx")
    sample = df.sample(30, random_state=7).reset_index(drop=True)

    print(f"Running variant A (no grounding instruction) on {len(sample)} reviews...")
    results_a = run_variant(sample, build_prompt_locked_tone, "A_no_grounding", api_key)

    print(f"\nRunning variant B (with grounding instruction) on {len(sample)} reviews...")
    results_b = run_variant(sample, build_prompt_locked_tone_with_grounding, "B_with_grounding", api_key)

    all_results = results_a + results_b
    out_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame(all_results).to_csv(os.path.join(out_dir, "ab_test_output.csv"), index=False)
    print(f"\nSaved -> {out_dir}/ab_test_output.csv")


if __name__ == "__main__":
    main()
