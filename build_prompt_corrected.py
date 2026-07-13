"""
User's edited prompt, corrected:
1. Response-length variable unified to a single spelling/casing throughout
   (was: {response_length}, {Response_length}, {Response_lenght} - three
   different variants across the two prompt sections).
2. Hardcoded "Rating: 5" in Variant A replaced with {StarRating} placeholder.
3. Rating-conditional Contact CTA restored (was present in the original C#
   code and in the last synthesized version; dropped somewhere during editing).

Grounding Instruction remains intentionally absent per explicit confirmation.
This means repetition control now rests entirely on the persona paragraphs
under each tone plus the standard "avoid generic corporate phrases" /
"vary structure" style instructions - NOT validated to work without the
Grounding Instruction. Flagged again at the bottom of this file.
"""

TONE_PERSONAS = {
    "Friendly": (
        "You are the friendly face of {business_name}. Respond to every review in a warm, "
        "approachable, and welcoming manner that makes customers feel valued and appreciated."
    ),
    "Professional": (
        "You are an official representative of {business_name}, tasked with responding to "
        "customer reviews on Google."
    ),
    "Empathetic": (
        "You are the customer care voice of {business_name}. Begin by acknowledging the "
        "customer's feelings and experience before addressing their feedback, ensuring they "
        "feel heard, understood, and respected."
    ),
    "Enthusiastic": (
        "You are the enthusiastic brand ambassador for {business_name}. Respond with genuine "
        "excitement, positivity, and appreciation while celebrating the customer's experience."
    ),
    "Confident": (
        "You are the trusted voice of {business_name}. Respond with clarity, assurance, and "
        "authority, inspiring confidence in the business while remaining respectful and "
        "solution-oriented."
    ),
    "Conversational": (
        "You are the approachable voice of {business_name}. Respond as though you're having a "
        "natural, one-on-one conversation with the customer, using relaxed, authentic, and "
        "easy-to-understand language."
    ),
}


def _contact_cta(rating: int, has_contact_info: bool) -> str:
    if not has_contact_info:
        return ""
    if rating <= 2:
        return "Guide the customer to contact support early in the response - do not bury it after lengthy empathy. The goal is to move the conversation to a private channel quickly."
    elif rating == 3:
        return "If appropriate, mention how the customer can reach out for further assistance."
    else:
        return "Include contact details only if the response naturally calls for it."


def build_prompt_default_tone(
    business_name: str,
    reviewer_name: str,
    rating: int,
    review_text: str,
    response_length: int,
    keyword1: str = "",
    keyword2: str = "",
    contact_number: str = "",
    website_url: str = "",
    signature: str = "",
) -> str:
    """Variant A: model selects tone from review content."""
    tone_options = "\n".join(
        f"{name}:\n{persona.format(business_name=business_name)}\n"
        for name, persona in TONE_PERSONAS.items()
    )

    has_contact_info = bool(contact_number or website_url)
    contact_cta = _contact_cta(rating, has_contact_info)

    token_lines = []
    if contact_number:
        token_lines.append(f"Contact Number: {contact_number}")
    if website_url:
        token_lines.append(f"Website URL: {website_url}")
    tokens_str = ", ".join(token_lines)

    keyword_str = ", ".join(k for k in [keyword1, keyword2] if k)
    keyword_block = ""
    if keyword_str:
        keyword_block = f"""
Keyword Instructions:

Keyword List:
{keyword_str}

From the keywords listed above, identify those that are contextually relevant to the review text.
Use up to 2 of the most relevant matches in the response.
Weave them into sentences where they fit the context.
Do not invent additional keywords.
Do not force keywords that are unrelated to the review.
"""

    prompt = f"""Select the most appropriate tone based primarily on the review content.
If the review text and star rating conflict, prioritize the review text over the rating.

Available tones:
{tone_options}
Choose the single tone that best matches the review.
Do not mention the selected tone in the response.

Customer Information:
Review Text: {review_text}
Rating: {rating}
Reviewer Name: {reviewer_name}

Rating Interpretation:
- 1-2 stars: Acknowledge feelings briefly, show care, and guide the customer to contact support. Be concise - do not write extended apologies. Priority is moving the conversation off the public thread.
- 3 stars: Respond with a balanced, constructive tone.
- 4-5 stars: Respond with appreciation grounded in specifics, not generic enthusiasm.

If the review text and star rating conflict, address what the customer actually wrote rather than the rating, without calling attention to the mismatch.

Response Requirements:
- Generate a response within {response_length} words.
- Match the selected tone consistently throughout.
- Avoid generic corporate phrases.
- Do not include hashtags or @mentions.
- Do not repeat, restate, or describe the customer's issue in your own words. Acknowledge feedback without amplifying complaint specifics.
- All resolution to customer complaints applies to the current feedback only, not future recurrence.
- Do not include staff names mentioned in the review, even positively.
- Do not paraphrase the review back to the customer.
- Do not invent facts or make unsupported promises.
{keyword_block}"""
    if tokens_str:
        prompt += f"\nInclude these tokens naturally if appropriate:\n{tokens_str}\n"
    if contact_cta:
        prompt += f"\n{contact_cta}\n"
    if signature:
        prompt += f"\nAppend this signature at the end if provided:\n{signature}\n"

    return prompt.strip()


def build_prompt_locked_tone(
    business_name: str,
    reviewer_name: str,
    rating: int,
    review_text: str,
    response_length: int,
    locked_tone: str,
    client_instructions: str = "",
    keyword1: str = "",
    keyword2: str = "",
    contact_number: str = "",
    website_url: str = "",
    signature: str = "",
) -> str:
    """Variant B: client has a locked tone (e.g. always 'Conversational')."""
    persona = TONE_PERSONAS[locked_tone].format(business_name=business_name)

    has_contact_info = bool(contact_number or website_url)
    contact_cta = _contact_cta(rating, has_contact_info)

    token_lines = []
    if contact_number:
        token_lines.append(f"Contact Number: {contact_number}")
    if website_url:
        token_lines.append(f"Website URL: {website_url}")
    tokens_str = ", ".join(token_lines)

    keyword_str = ", ".join(k for k in [keyword1, keyword2] if k)
    keyword_block = ""
    if keyword_str:
        keyword_block = f"""
Keyword Instructions:

Keyword List:
{keyword_str}

From the keywords listed above, identify those that are contextually relevant to the review text.
Use up to 2 of the most relevant matches in the response.
Weave them into sentences where they fit the context.
Do not invent additional keywords.
Do not force keywords that are unrelated to the review.
"""

    client_instructions_block = (
        f"\nClient Instructions:\n{client_instructions.strip()}\n" if client_instructions.strip() else ""
    )

    prompt = f"""{persona}
{client_instructions_block}
Customer Information:
Review Text: {review_text}
Rating: {rating}
Reviewer Name: {reviewer_name}

Rating Interpretation:
- 1-2 stars: Acknowledge feelings briefly, show care, and guide the customer to contact support. Be concise - do not write extended apologies. Priority is moving the conversation off the public thread.
- 3 stars: Respond with a balanced, constructive tone.
- 4-5 stars: Respond with appreciation grounded in specifics, not generic enthusiasm.

If the review text and star rating conflict, address what the customer actually wrote rather than the rating, without calling attention to the mismatch.

Response Requirements:
- Generate a response within {response_length} words.
- Do not include hashtags or @mentions.
- Do not repeat, restate, or describe the customer's issue in your own words. Acknowledge feedback without amplifying complaint specifics.
- All resolution to customer complaints applies to the current feedback only, not future recurrence.
- Do not include staff names mentioned in the review, even positively.
- Do not paraphrase the review back to the customer.
- Do not invent facts or make unsupported promises.
{keyword_block}"""
    if tokens_str:
        prompt += f"\nInclude these tokens naturally if appropriate:\n{tokens_str}\n"
    if contact_cta:
        prompt += f"\n{contact_cta}\n"
    if signature:
        prompt += f"\nAppend this signature at the end if provided:\n{signature}\n"

    return prompt.strip()


# ---------------------------------------------------------------------------
# STILL OPEN, NOT SILENTLY RESOLVED:
#
# - No Grounding Instruction, confirmed intentional. Repetition control here
#   depends entirely on the persona paragraphs + generic style instructions.
#   The "Enthusiastic" persona in particular ("genuine excitement, positivity,
#   and appreciation... celebrating") uses close kin to the adjective
#   cluster that produced 98% "thrilled" in the original diagnosed data.
#   This is a real risk carried forward, not resolved by removing the ban
#   list or adding personas - it needs to be measured, not assumed.
#
# - This file has NOT been run against a live model. Do that before treating
#   either variant as production-ready.
# ---------------------------------------------------------------------------
