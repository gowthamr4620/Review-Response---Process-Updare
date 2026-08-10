"""
Deterministically matches the approved keyword vocabulary against the review
text BEFORE the prompt is built, so the model never decides what counts as a
"keyword" — it only ever sees words already confirmed present in the review.
Matching is whole-word, case-insensitive, ordered by first appearance in the
review, capped at top_n. Direct port of GetTopMatchingKeywords.

KNOWN LIMITATION (carried over from the source): naive whole-word matching
won't catch inflections (e.g. approved keyword "helpful" won't match review
text "helped"). If the approved list is large or recall matters, consider
stemming or fuzzy matching.
"""

import re
from typing import List, Optional, Sequence


def get_top_matching_keywords(
    review_text: Optional[str],
    approved_keywords: Optional[Sequence[str]],
    top_n: int,
) -> List[str]:
    if not review_text or not review_text.strip() or not approved_keywords:
        return []

    matches = []
    for keyword in approved_keywords:
        if not keyword or not keyword.strip():
            continue
        match = re.search(rf"\b{re.escape(keyword)}\b", review_text, re.IGNORECASE)
        if match:
            matches.append((match.start(), keyword))

    matches.sort(key=lambda pair: pair[0])
    return [keyword for _, keyword in matches[:top_n]]
