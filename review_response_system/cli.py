"""
CLI for the review response system. Takes the four uploaded inputs as
separate JSON files — Business Info, Review Details, Keywords, and
Signature & Customer Support Details — builds the prompt, calls the LLM,
and prints the generated response.

Usage:
    export OPENAI_API_KEY=sk-...
    python -m review_response_system.cli \\
        --business examples/business_info.json \\
        --review examples/review_details.json \\
        --keywords examples/keywords.json \\
        --support examples/support_details.json

Pass --dry-run to print the built prompt and sampling params instead of
calling the LLM (useful for reviewing the prompt before spending a call).
"""

from __future__ import annotations

import argparse
import json
import sys

from .core.generate_response import generate_review_response
from .core.models import (
    AIResponseLengthType,
    BusinessInfo,
    Keywords,
    ReviewDetails,
    ReviewResponseRequest,
    SignatureSupportDetails,
)
from .core.prompt_builder import build_review_response_prompt


def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_request(business_path: str, review_path: str, keywords_path: str, support_path: str) -> ReviewResponseRequest:
    business_data = _load_json(business_path)
    review_data = _load_json(review_path)
    keywords_data = _load_json(keywords_path) if keywords_path else {}
    support_data = _load_json(support_path) if support_path else {}

    business_info = BusinessInfo(business_name=business_data["business_name"])

    review_details = ReviewDetails(
        reviewer_name=review_data["reviewer_name"],
        rating=review_data["rating"],
        review=review_data.get("review"),
        ai_response_length_type=AIResponseLengthType(review_data.get("ai_response_length_type", "Default")),
    )

    keywords = Keywords(approved_keywords=keywords_data.get("approved_keywords", []))

    support_details = SignatureSupportDetails(
        signature=support_data.get("signature"),
        contact_number=support_data.get("contact_number"),
        support_email=support_data.get("support_email"),
        website_url=support_data.get("website_url"),
    )

    return ReviewResponseRequest(
        business_info=business_info,
        review_details=review_details,
        keywords=keywords,
        support_details=support_details,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--business", required=True, help="Path to Business Info JSON")
    parser.add_argument("--review", required=True, help="Path to Review Details JSON")
    parser.add_argument("--keywords", default=None, help="Path to Keywords JSON")
    parser.add_argument("--support", default=None, help="Path to Signature & Customer Support Details JSON")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model to use")
    parser.add_argument("--dry-run", action="store_true", help="Print the built prompt instead of calling the LLM")
    args = parser.parse_args()

    request = _build_request(args.business, args.review, args.keywords, args.support)

    if args.dry_run:
        chat_request = build_review_response_prompt(request, model=args.model)
        print(f"--- model: {chat_request.model} ---")
        print(f"temperature={chat_request.temperature} max_tokens={chat_request.max_tokens} "
              f"frequency_penalty={chat_request.frequency_penalty} presence_penalty={chat_request.presence_penalty}")
        print("--- prompt ---")
        print(chat_request.prompt)
        return

    try:
        response_text = generate_review_response(request, model=args.model)
    except Exception as exc:  # surfaced to the caller, not swallowed
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(response_text)


if __name__ == "__main__":
    main()
