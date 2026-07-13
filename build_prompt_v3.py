"""
Refinement targeting the SPECIFIC failure found in real output (candere_corrected_output.xlsx):
- "means a lot to us" in 89% of responses
- "hope to see you again soon" in ~50%
- "thank you so much for taking the time" in ~40-47%

Diagnosis: most sample reviews are short, generically positive 5-star
compliments with little distinctive material. When the review gives the
model nothing unusual to react to, it falls back to a fixed 3-beat template
(thank -> generic validation -> invite back). The fix has two parts:

1. Force extraction of ONE concrete noun/phrase from the review BEFORE
   writing anything else - even a short generic-sounding review almost
   always has at least one (a product type, a staff name reference, a
   specific service word). This gives the model material to build the
   opening from instead of defaulting to boilerplate when the review is
   thin.

2. Name and prohibit the exact two template slots found in real output
   (the gratitude-closing phrase family, the "see you again" invitation
   family) rather than a generic "avoid corporate phrases" instruction -
   specific, evidenced prohibitions are harder to route around than vague
   ones, because the model can't satisfy "be specific" while still using
   a banned slot, whereas it clearly could satisfy "avoid generic phrases"
   while still writing "means a lot to us" (that phrase doesn't read as
   obviously corporate/generic on its own).
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


def build_prompt_locked_tone_v3(
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
    persona = TONE_PERSONAS[locked_tone].format(business_name=business_name)

    has_contact_info = bool(contact_number or website_url)
    contact_cta = _contact_cta(rating, has_contact_info)

    token_lines = []
    if contact_number:
        token_lines.append(f"Contact Number: {contact_number}")
    if website_url:
        token_lines.append(f"Website URL: {website_url}")
    tokens_str = ", ".join(token_lines)

    client_instructions_block = (
        f"\nClient Instructions:\n{client_instructions.strip()}\n" if client_instructions.strip() else ""
    )

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

    # --- Sole anti-repetition mechanism: forced extraction anchored to the
    # review's own text, not a maintained ban list. The first sentence must
    # contain or closely paraphrase something actually present in the
    # review - this scales with input data instead of needing manual
    # updates every time the model finds a new default phrase. ---
    extraction_instruction = """
Before writing the response, find one specific word, phrase, or detail that appears in the review text itself - a product mentioned, a specific moment described, or a distinctive word the customer used. Your first sentence must directly reference or closely paraphrase that specific detail - not a general thank-you or a statement of how much the review means to you. If the review is short or generic, still find the one most concrete thing in it and build the opening around that rather than falling back on a general expression of gratitude."""

    prompt = f"""{persona}
{client_instructions_block}
Customer Information:
Review Text: {review_text}
Rating: {rating}
Reviewer Name: {reviewer_name}
{extraction_instruction}

Rating Interpretation:
- 1-2 stars: Acknowledge feelings briefly, show care, and guide the customer to contact support. Be concise - do not write extended apologies. Priority is moving the conversation off the public thread.
- 3 stars: Respond with a balanced, constructive tone.
- 4-5 stars: Respond with appreciation grounded in the specific detail identified above, not generic enthusiasm or gratitude.

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
