"""
Prompt builder — the structural framework for review responses. Ported from
the reference C# PrepareOpenAIReviewRequest, section for section:

  voice instruction        -> first-person-plural brand voice, no individual persona
  guardrail instruction    -> no amplifying complaints, no paraphrasing the
                               review, no staff names, no promises beyond
                               this customer's experience
  tone instruction         -> model picks the best-fit tone from a fixed list
  sentiment instruction    -> rating-band-specific handling, gated by
                               deterministically-matched approved keywords
  review section           -> the review being responded to
  length settings          -> per-AIResponseLengthType instruction + sampling
                               params (frequency/presence penalty, temperature,
                               max_tokens)

Everything upstream of this module (models.py, sentiment.py,
keyword_matcher.py) exists to feed this function; this is the only place the
final prompt string is assembled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .keyword_matcher import get_top_matching_keywords
from .models import AIResponseLengthType, ReviewResponseRequest
from .sentiment import ReviewSentimentBand, get_sentiment_band


@dataclass
class PromptSettings:
    instruction: str
    keyword_count: int
    frequency_penalty: float
    presence_penalty: float
    temperature: float
    max_tokens: int


@dataclass
class ChatCompletionRequest:
    """Mirrors the C# OpenAIChatRequest shape this prompt is built for."""
    model: str
    prompt: str
    frequency_penalty: float
    presence_penalty: float
    temperature: float
    max_tokens: int


TONE_INSTRUCTION = """\
Select the most appropriate tone based primarily on the review content.
If the review text and star rating conflict, prioritize the review text over the rating.

Available tones:
- Friendly:
  Warm, approachable, and personable, while still speaking as the business ("we").
  Focuses on building a positive connection with the customer.
- Professional:
  Polished, respectful, and business-appropriate. Clear and confident without sounding
  overly formal, robotic, or cold.
- Empathetic:
  Leads with genuine acknowledgement of the customer's feelings, concerns, or experience
  before offering appreciation, explanation, or resolution.
- Enthusiastic:
  High-energy, positive, and celebratory. Expresses genuine excitement and appreciation
  for exceptional feedback or experiences.
- Confident:
  Direct, assured, and authoritative. Demonstrates accountability and expertise without
  over-apologizing, hedging, or sounding defensive.
- Conversational:
  Natural, relaxed, and easy to read rather than a stiff, formal statement, while still
  speaking as the business ("we") rather than as an individual.

Choose the single tone that best matches the review content and customer sentiment.
If the review is negative (1-2 stars), temper the selected tone's energy so it does not
read as celebratory or dismissive of the complaint.
Do not mention the selected tone in the response."""

GUARDRAIL_INSTRUCTION = """\
Non-negotiable response rules:
- Acknowledge the customer's feelings or experience without repeating or amplifying the
  specific details of their complaint.
- Do not paraphrase or summarize the review's content back to the customer. The only
  exception is a pre-approved keyword explicitly provided to you elsewhere in this
  prompt — those may be used, but do not lift any other wording from the review.
- Do not name any staff member mentioned in the review, even if the mention is positive.
- Any resolution, apology, or improvement language must apply only to this customer's
  specific experience. Do not imply a policy change, a systemic fix, or a promise to
  future customers."""


def _voice_instruction(business_name: str) -> str:
    return (
        f"You are writing this response on behalf of {business_name} as a business —\n"
        "not as an individual employee or representative.\n"
        'Use first-person plural only ("we", "us", "our"). Never use "I", "I\'m", "I\'ll", "I\'ve",\n'
        "or any other singular first-person pronoun, anywhere in the response.\n"
        "Keep this voice consistent from the first word to the last — do not switch between\n"
        "singular and plural partway through."
    )


def _prompt_settings(length_type: AIResponseLengthType, review_text_exists: bool) -> PromptSettings:
    if length_type == AIResponseLengthType.CONCISE:
        return PromptSettings(
            instruction=(
                "Craft a response based on the review content and rating within 50 words."
                if review_text_exists
                else "Generate a personalized response based on the rating within 25 words."
            ),
            keyword_count=2,
            frequency_penalty=0.9,
            presence_penalty=0.8,
            temperature=0.8,
            max_tokens=70,
        )

    if length_type == AIResponseLengthType.ELABORATE:
        return PromptSettings(
            instruction=(
                "Write a detailed response for the review within 150 words."
                if review_text_exists
                else "Generate a detailed response based on the rating within 80 words."
            ),
            keyword_count=3,
            frequency_penalty=1.0,
            presence_penalty=0.8,
            temperature=0.8 if review_text_exists else 0.75,
            max_tokens=200,
        )

    return PromptSettings(
        instruction=(
            "Generate a personalized response based on the review text and rating within 80 words."
            if review_text_exists
            else "Generate a response based on the star rating within 40 words."
        ),
        keyword_count=3,
        frequency_penalty=0.9,
        presence_penalty=0.8,
        temperature=0.8,
        max_tokens=110,
    )


def _sentiment_instruction(band: ReviewSentimentBand, matched_keywords: List[str]) -> str:
    if not matched_keywords and band != ReviewSentimentBand.NEGATIVE:
        if band == ReviewSentimentBand.NEUTRAL:
            return (
                "This is a mixed or neutral review (3 stars). Acknowledge both what the "
                "customer appreciated and their concern, without restating specific complaint "
                "details or any wording from the review itself."
            )
        return (
            "This is a positive review (4-5 stars). Express genuine appreciation for the "
            "customer's experience. Keep the length and energy matched to the selected "
            "style — do not add a closing sentence that restates a point already made "
            "earlier in the response."
        )

    if band == ReviewSentimentBand.NEGATIVE:
        return """\
This is a negative review (1-2 stars).
Lead with genuine acknowledgement of the customer's frustration before anything else.
Do not mention specific details, product terms, or complaint language drawn from the
review text — acknowledge the sentiment generically instead. No approved keywords
are used on negative reviews, regardless of whether any matched.
Keep the tone measured and accountable, even if the selected style is normally
upbeat — do not open with celebratory or high-energy language.
Invite the customer to continue the conversation directly (e.g. via direct contact)
rather than resolving specifics in the public response."""

    if band == ReviewSentimentBand.NEUTRAL:
        return (
            "This is a mixed or neutral review (3 stars).\n"
            "Acknowledge both what the customer appreciated and their concern, without restating\n"
            "specific complaint details or any other wording from the review.\n"
            "You may use this approved keyword, since it is confirmed present in the review and\n"
            f"pre-cleared for use: {matched_keywords[0]}.\n"
            "Do not use any other word or phrase drawn from the review text."
        )

    return (
        "This is a positive review (4-5 stars).\n"
        "Express genuine appreciation. Where it fits naturally, work in these approved\n"
        "keywords, since they are confirmed present in the review and pre-cleared for use:\n"
        f"{', '.join(matched_keywords)}.\n"
        "Do not use any other word or phrase drawn from the review text.\n"
        "Keep the length and energy matched to the selected style — do not add a closing\n"
        "sentence that restates a point already made earlier in the response."
    )


def _review_section(request: ReviewResponseRequest) -> str:
    details = request.review_details
    lines = []
    if details.review_text_exists:
        lines.append(f"Review Text: {details.review}")
    lines.append(f"Rating: {details.rating}")
    lines.append(f"Reviewer Name: {details.reviewer_name}")
    lines.append(f"Business Name: {request.business_info.business_name}")
    return "\n".join(lines)


def build_review_response_prompt(
    request: ReviewResponseRequest,
    model: str = "gpt-4.1-mini",
) -> ChatCompletionRequest:
    details = request.review_details
    review_text_exists = details.review_text_exists

    sentiment_band = get_sentiment_band(details.rating)
    settings = _prompt_settings(details.ai_response_length_type, review_text_exists)

    matched_keywords = (
        get_top_matching_keywords(details.review, request.keywords.approved_keywords, settings.keyword_count)
        if review_text_exists
        else []
    )

    base_prompt = (
        f"{_voice_instruction(request.business_info.business_name)}\n\n{GUARDRAIL_INSTRUCTION}\n\n"
        "Craft the response in a warm and thoughtful tone consistent with the business's brand voice. "
        "Avoid formal clichés or overused corporate phrases."
    )

    sentiment_instruction = _sentiment_instruction(sentiment_band, matched_keywords)
    review_section = _review_section(request)
    tokens_line = request.support_details.as_tokens_line()

    prompt_parts = [
        base_prompt,
        TONE_INSTRUCTION,
        sentiment_instruction,
        review_section,
        settings.instruction,
        "Do not include any email addresses, hashtags, or @mentions inside the main response text.",
    ]
    if tokens_line:
        prompt_parts.append(f"Include {tokens_line} inside the response.")
    if request.support_details.signature:
        prompt_parts.append(f"Include {request.support_details.signature} at the end if available.")

    prompt = "\n\n".join(prompt_parts)

    return ChatCompletionRequest(
        model=model,
        prompt=prompt,
        frequency_penalty=settings.frequency_penalty,
        presence_penalty=settings.presence_penalty,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
    )
