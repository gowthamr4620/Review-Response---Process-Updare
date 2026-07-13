"""
Repetition diagnostic - run this against output CSVs from run_batch.py.

This is the same check applied to the original Candere export that revealed
82/100 "Hi [name]" opens and 98/100 containing "thrilled". Use this every
time you test a prompt change, and periodically in production (this is the
human-in-the-loop audit that replaces a maintained ban list).

Usage:
    python scripts/diagnose_repetition.py output/candere_output.csv
    python scripts/diagnose_repetition.py output/combined_output.csv --by-client
"""

import argparse
import re
from collections import Counter

import pandas as pd


def analyze(df: pd.DataFrame, label: str):
    n = len(df)
    if n == 0:
        print(f"\n=== {label}: no rows ===")
        return

    resp = df["response"].astype(str)
    resp = resp[~resp.str.startswith("ERROR")]
    err_count = n - len(resp)

    print(f"\n=== {label} (n={n}, errors={err_count}) ===")

    if len(resp) == 0:
        print("All rows errored - nothing to analyze.")
        return

    # Opening word / opening bigram distribution
    opens = resp.str.strip().str.split().str[0].str.strip(".,!").str.lower()
    print("\n-- Opening word distribution --")
    top_opens = opens.value_counts().head(8)
    print(top_opens.to_string())
    max_open_share = top_opens.iloc[0] / len(resp) if len(top_opens) else 0
    flag = "  <-- FLAG: >30% share, still converging" if max_open_share > 0.30 else ""
    print(f"Top opening word share: {max_open_share:.0%}{flag}")

    # Opening structural pattern: greet-then-thank
    greet_then_thank = resp.str.lower().str.match(r"^(hi|hey|hello)\b[^.!?]{0,25}(thank|thanks)")
    gt_count = greet_then_thank.sum()
    flag2 = "  <-- FLAG: structural template still present" if gt_count / len(resp) > 0.15 else ""
    print(f"'Greet then thank' opening pattern: {gt_count}/{len(resp)} ({gt_count/len(resp):.0%}){flag2}")

    # Generic sentiment-word concentration (post-fix check, not a maintained
    # ban list - just measuring whether the model naturally drifted to a
    # new dominant word despite no explicit ban)
    words = Counter()
    for r in resp.str.lower():
        for w in re.findall(r"[a-z']+", r):
            if len(w) > 4:
                words[w] += 1
    print("\n-- Most frequent words (5+ letters, rough proxy for drift) --")
    for w, c in words.most_common(12):
        share = c / len(resp)
        flag3 = "  <-- watch this one" if share > 0.4 else ""
        print(f"  {w}: {c} ({share:.0%} of responses){flag3}")

    # Length sanity
    word_counts = resp.str.split().str.len()
    print(f"\n-- Length --\nmean words: {word_counts.mean():.0f}, min: {word_counts.min()}, max: {word_counts.max()}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--by-client", action="store_true", help="Break down separately per client_id column")
    args = parser.parse_args()

    df = pd.read_csv(args.csv_path)

    if args.by_client and "client_id" in df.columns:
        for client_id, sub in df.groupby("client_id"):
            analyze(sub, f"Client: {client_id}")
        analyze(df, "ALL CLIENTS COMBINED (cross-client repetition check)")
    else:
        analyze(df, args.csv_path)


if __name__ == "__main__":
    main()
