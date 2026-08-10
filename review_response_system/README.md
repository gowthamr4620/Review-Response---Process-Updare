# Review Response System

Generates review responses from four uploaded inputs — **Business Info**,
**Review Details**, **Keywords**, and **Signature & Customer Support
Details** — using an LLM API. The prompt builder (`core/prompt_builder.py`)
is a direct Python port of the reference C# `PrepareOpenAIReviewRequest`
structure and carries over its guardrails unchanged.

## Structure

```
core/
  models.py            - the four upload categories, as typed inputs
  sentiment.py          - buckets a rating into Negative/Neutral/Positive
  keyword_matcher.py     - deterministic approved-keyword matching against review text
  prompt_builder.py      - assembles the structural prompt + sampling params
  llm_client.py           - calls the OpenAI Chat Completions API
  generate_response.py    - build prompt -> call LLM -> return response text
examples/
  business_info.json, review_details.json, keywords.json, support_details.json
tests/
  unit tests for keyword matching, sentiment banding, and prompt structure
cli.py
```

## The four uploaded inputs

| Input | File | Fields |
|---|---|---|
| Business Info | `business_info.json` | `business_name` |
| Review Details | `review_details.json` | `reviewer_name`, `rating` (1-5), `review` (optional), `ai_response_length_type` (`Concise` / `Default` / `Elaborate`) |
| Keywords | `keywords.json` | `approved_keywords` — a pre-approved vocabulary for this business/category |
| Signature & Customer Support Details | `support_details.json` | `signature`, `contact_number`, `support_email`, `website_url` |

Keywords are never freely extracted by the model. `keyword_matcher.py` runs
**before** the prompt is built and only passes through approved keywords that
are deterministically confirmed present in the review text (whole-word,
case-insensitive). Negative reviews (1-2 stars) never receive keywords,
regardless of matches, per the guardrail in the prompt.

## Prompt structure (what `prompt_builder.py` assembles, in order)

1. **Voice instruction** — first-person plural only ("we/us/our"); the
   business voice, never an individual's.
2. **Guardrails** — no amplifying complaint specifics, no paraphrasing the
   review (except pre-approved keywords), no staff names, no promises beyond
   this customer's experience.
3. **Tone instruction** — the model picks the best-fit tone from a fixed
   list (Friendly, Professional, Empathetic, Enthusiastic, Confident,
   Conversational), tempered on negative reviews.
4. **Sentiment instruction** — rating-band-specific handling, gated by the
   matched approved keywords.
5. **Review section** — reviewer name, rating, review text (if present),
   business name.
6. **Length settings** — per `ai_response_length_type`: word-count
   instruction plus `temperature` / `frequency_penalty` / `presence_penalty`
   / `max_tokens`.
7. **Formatting + support details** — no emails/hashtags/@mentions in the
   body; contact details and signature appended if provided.

## Running it

```bash
export OPENAI_API_KEY=sk-...

# Review the built prompt without spending a call:
python -m review_response_system.cli \
  --business review_response_system/examples/business_info.json \
  --review review_response_system/examples/review_details.json \
  --keywords review_response_system/examples/keywords.json \
  --support review_response_system/examples/support_details.json \
  --dry-run

# Generate a response for real:
python -m review_response_system.cli \
  --business review_response_system/examples/business_info.json \
  --review review_response_system/examples/review_details.json \
  --keywords review_response_system/examples/keywords.json \
  --support review_response_system/examples/support_details.json
```

Run from the repository root. `--keywords` and `--support` are optional —
omit them for a business with no approved vocabulary or no support/signature
details to include.

## Programmatic use

```python
from review_response_system.core import (
    BusinessInfo, ReviewDetails, Keywords, SignatureSupportDetails,
    ReviewResponseRequest, generate_review_response, AIResponseLengthType,
)

request = ReviewResponseRequest(
    business_info=BusinessInfo(business_name="Candere"),
    review_details=ReviewDetails(
        reviewer_name="Priya", rating=5,
        review="Loved the necklace, arrived beautifully packaged.",
        ai_response_length_type=AIResponseLengthType.DEFAULT,
    ),
    keywords=Keywords(approved_keywords=["necklace", "packaged"]),
    support_details=SignatureSupportDetails(signature="Regards, Candere"),
)

response_text = generate_review_response(request)  # calls OpenAI
```

## Tests

```bash
python -m unittest discover -s review_response_system/tests -t .
```

No network calls are made by the test suite — it covers keyword matching,
sentiment banding, and prompt structure only. `llm_client.py` is exercised
only via the CLI/`generate_review_response`, against a real API key.

## Known limitation (carried over from the source)

Keyword matching is whole-word, not stemmed — an approved keyword like
"helpful" will not match review text like "helped". If recall on inflected
forms matters, add stemming or fuzzy matching to `keyword_matcher.py`.

## Open question from the source C# file

The reference implementation flagged that `ApprovedKeywords` needs a
confirmed source: is it a field on the incoming request DTO, or a
per-business/category lookup done separately and passed in? This port
treats it as an explicit upload (`keywords.json`) to stay unblocked, but
that's a placeholder for wherever the real approved-vocabulary store ends up
living.
