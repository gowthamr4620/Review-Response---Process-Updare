"""
Compares Variant A (no grounding instruction) vs Variant B (with grounding
instruction) on the same 30 Candere reviews, same tone/length/signature.

Usage:
    python diagnose_ab.py output/ab_test_output.csv
"""

import argparse
import re
from collections import Counter

import pandas as pd


def analyze(df: pd.DataFrame, label: str):
    n = len(df)
    resp = df["response"].astype(str)
    resp = resp[~resp.str.startswith("ERROR")]
    err_count = n - len(resp)

    print(f"\n=== {label} (n={n}, errors={err_count}) ===")
    if len(resp) == 0:
        print("All rows errored.")
        return

    opens = resp.str.strip().str.split().str[0].str.strip(".,!").str.lower()
    top_opens = opens.value_counts().head(6)
    print("-- Opening word distribution --")
    print(top_opens.to_string())
    max_share = top_opens.iloc[0] / len(resp) if len(top_opens) else 0
    print(f"Top opening word share: {max_share:.0%}")

    greet_then_thank = resp.str.lower().str.match(r"^(hi|hey|hello)\b[^.!?]{0,25}(thank|thanks)")
    gt = greet_then_thank.sum()
    print(f"'Greet then thank' opening pattern: {gt}/{len(resp)} ({gt/len(resp):.0%})")

    words = Counter()
    for r in resp.str.lower():
        for w in re.findall(r"[a-z']+", r):
            if len(w) > 4:
                words[w] += 1
    print("-- Top words (5+ letters) --")
    for w, c in words.most_common(10):
        print(f"  {w}: {c} ({c/len(resp):.0%})")

    word_counts = resp.str.split().str.len()
    print(f"-- Length -- mean: {word_counts.mean():.0f}, min: {word_counts.min()}, max: {word_counts.max()}")


def print_samples(df: pd.DataFrame, variant: str, n=5):
    sub = df[df["variant"] == variant].head(n)
    print(f"\n--- Sample responses: {variant} ---")
    for _, row in sub.iterrows():
        print(f"\nReview ({row['rating']}★): {row['review'][:100]}")
        print(f"Response: {row['response']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()

    df = pd.read_csv(args.csv_path)

    for variant in df["variant"].unique():
        analyze(df[df["variant"] == variant], variant)

    for variant in df["variant"].unique():
        print_samples(df, variant, args.samples)


if __name__ == "__main__":
    main()
