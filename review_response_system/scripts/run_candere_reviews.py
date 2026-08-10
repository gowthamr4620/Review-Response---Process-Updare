"""
One-off batch run: generate responses for the reviews in
Candere_Reviews__Sample_Responses.xlsx, using a locked, rating-based tone
mapping (not the model-selected default):

    1-2 stars -> Empathetic
    3 stars   -> Conversational
    4-5 stars -> Friendly

No ReviewerName column exists in this export, so "Customer" is used as a
generic placeholder. Keywords/support-details inputs are omitted (Candere's
example config in examples/support_details.json is reused for signature +
contact info).

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/run_candere_reviews.py <input.xlsx> <output.xlsx>
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from review_response_system.core import (
    AIResponseLengthType,
    BusinessInfo,
    Keywords,
    ReviewDetails,
    ReviewResponseRequest,
    SignatureSupportDetails,
    Tone,
    generate_review_response,
)

RATING_TONE_MAP = {
    1: Tone.EMPATHETIC,
    2: Tone.EMPATHETIC,
    3: Tone.CONVERSATIONAL,
    4: Tone.FRIENDLY,
    5: Tone.FRIENDLY,
}

BUSINESS_INFO = BusinessInfo(business_name="Candere")
SUPPORT_DETAILS = SignatureSupportDetails(
    signature="Regards, Candere - A Kalyan Company",
    contact_number="2261066262",
    support_email="support@candere.com",
)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python run_candere_reviews.py <input.xlsx> <output.xlsx>", file=sys.stderr)
        sys.exit(1)

    input_path, output_path = sys.argv[1], sys.argv[2]

    wb = openpyxl.load_workbook(input_path)
    ws = wb.active
    header = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    col = {name: idx for idx, name in enumerate(header)}

    ws.cell(row=1, column=len(header) + 1, value="LockedTone")
    ws.cell(row=1, column=len(header) + 2, value="GeneratedResponse")

    rows = list(ws.iter_rows(min_row=2))
    total = len(rows)
    for i, row in enumerate(rows, start=1):
        rating = row[col["rating"]].value
        review_text = row[col["ReviewContent"]].value or None
        tone = RATING_TONE_MAP[rating]

        review_details = ReviewDetails(
            reviewer_name="Customer",
            rating=rating,
            review=review_text,
            ai_response_length_type=AIResponseLengthType.DEFAULT,
            locked_tone=tone,
        )
        request = ReviewResponseRequest(
            business_info=BUSINESS_INFO,
            review_details=review_details,
            keywords=Keywords(),
            support_details=SUPPORT_DETAILS,
        )

        try:
            response_text = generate_review_response(request, provider="anthropic")
        except Exception as exc:
            response_text = f"ERROR: {exc}"

        ws.cell(row=row[0].row, column=len(header) + 1, value=tone.value)
        ws.cell(row=row[0].row, column=len(header) + 2, value=response_text)

        print(f"[{i}/{total}] rating={rating} tone={tone.value} -> {response_text[:60]!r}...")

    wb.save(output_path)
    print(f"Saved -> {output_path}")


if __name__ == "__main__":
    main()
