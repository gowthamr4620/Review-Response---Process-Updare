import hashlib
from client_config_schema import ClientReviewResponseConfig, ClientTone, ClientLength, LENGTH_WORD_LIMITS
from persona_pools import get_persona

# ---------------------------------------------------------------------------
# PLATFORM-OWNED. Not exposed to clients. This is the entire repetition-control
# surface: persona/voice variety, banned words, grounding rule, structural
# variety. Clients only ever pick a ClientTone/ClientLength value; everything
# below is how the platform executes that choice differently every time.
#
# Persona pools (persona_pools.py) are the SOLE mechanism for tone direction -
# there is deliberately no separate generic "tone instruction" layer. A
# persona already embodies its tone; stacking a bare adjective-based
# instruction on top would be redundant and risks fighting the persona
# stylistically.
# ---------------------------------------------------------------------------

RESPONSE_OBJECTIVE_POOLS = {
    (ClientLength.CONCISE, True): [
        "In {word_limit} words or fewer, respond to the single most specific point in the review.",
        "Write a short reply, under {word_limit} words, that reacts to one concrete detail from the review rather than summarizing it.",
    ],
    (ClientLength.DEFAULT, True): [
        "In under {word_limit} words, respond directly to the specific points raised, without restating them.",
        "Write a reply under {word_limit} words that reacts naturally to what was actually said, not to the rating.",
    ],
    (ClientLength.ELABORATE, True): [
        "Write a fuller reply, up to {word_limit} words, that engages with two or more specific details from the review.",
        "In up to {word_limit} words, respond to the review's specifics in a way that feels considered, not padded.",
    ],
    (ClientLength.CONCISE, False): [
        "Write a short, specific-feeling reply under {word_limit} words based on the rating alone - avoid generic phrasing since there's no review text to react to.",
    ],
    (ClientLength.DEFAULT, False): [
        "Write a reply under {word_limit} words appropriate to the rating - keep it grounded and low-key since there's no review text to reference.",
    ],
    (ClientLength.ELABORATE, False): [
        "Write a fuller reply, up to {word_limit} words, appropriate to the rating, avoiding generic reassurance language since there's no review text to draw from.",
    ],
}

def get_default_tone(rating: int) -> ClientTone:
    return {
        5: ClientTone.ENTHUSIASTIC, 4: ClientTone.FRIENDLY, 3: ClientTone.CONVERSATIONAL,
        2: ClientTone.EMPATHETIC, 1: ClientTone.EMPATHETIC,
    }.get(rating, ClientTone.PROFESSIONAL)


def _stable_index(key: str, n: int) -> int:
    """Deterministic pseudo-random index from a stable key. Same (client_id,
    review_id) always resolves to the same variant - reproducible for QA/
    debugging - while different reviews and different clients spread across
    the pool instead of converging."""
    h = hashlib.sha256(key.encode()).hexdigest()
    return int(h, 16) % n


def get_response_objective(client_id: str, review_id: str, length: ClientLength,
                            review_text_exists: bool, word_limit: int) -> str:
    pool = RESPONSE_OBJECTIVE_POOLS[(length, review_text_exists)]
    idx = _stable_index(f"objective::{client_id}::{review_id}", len(pool))
    return pool[idx].format(word_limit=word_limit)


def build_review_prompt(
    config: ClientReviewResponseConfig,
    reviewer_name: str,
    rating: int,
    review_text: str | None,
    review_id: str,
    previous_responses: list[str] | None = None,
) -> str:
    review_text_exists = bool(review_text and review_text.strip())
    word_limit = LENGTH_WORD_LIMITS[config.length]

    persona = get_persona(config.tone)
    response_objective = get_response_objective(
        config.client_id, review_id, config.length, review_text_exists, word_limit
    )

    review_section = f"Review Text: {review_text}\n" if review_text_exists else ""

    keyword_count = {ClientLength.CONCISE: 1, ClientLength.DEFAULT: 2, ClientLength.ELABORATE: 3}[config.length]
    keyword_section = ""
    if config.brand_keywords and review_text_exists:
        keyword_section = f"""
Brand Keywords:
[{", ".join(config.brand_keywords)}]

From the keywords listed above, identify those that are contextually relevant to the review text.
Use up to {keyword_count} of the most relevant matches in the response.
Weave them into sentences where they fit the context - do not force-fit, list, or highlight them.
If none are relevant to the review, do not use any.
"""

    token_lines = []
    if config.contact_number:
        token_lines.append(f"- Contact Number: {config.contact_number}")
    if config.support_email:
        token_lines.append(f"- Support Email: {config.support_email}")
    if config.website_url:
        token_lines.append(f"- Website URL: {config.website_url}")
    has_contact_info = bool(token_lines)
    tokens_section = ""
    if has_contact_info:
        tokens_section = "\nBusiness Contact Details:\n" + "\n".join(token_lines)

    if has_contact_info:
        if rating <= 2:
            contact_cta = "Guide the customer to contact support early in the response - do not bury it after lengthy empathy. The goal is to move the conversation to a private channel quickly."
        elif rating == 3:
            contact_cta = "If appropriate, mention how the customer can reach out for further assistance."
        else:
            contact_cta = "Include contact details only if the response naturally calls for it."
    else:
        contact_cta = ""

    signature_section = f"\n\nSign off with exactly: {config.signature}" if config.signature else ""

    previous_section = ""
    if previous_responses:
        previous_section = "\nRecently Generated Responses for This Business (do not reuse phrasing, sentence openings, or structure from these):\n" + "\n---\n".join(previous_responses)

    client_instructions_section = ""
    if config.custom_instructions and config.custom_instructions.strip():
        client_instructions_section = f"""
Client-Specific Response Guidance (how this business wants responses handled):
{config.custom_instructions.strip()}

Note: the above is guidance on content and phrasing style for this business.
It does not override the anti-repetition and grounding rules below.
"""

    prompt = f"""{persona}

You're replying to a Google review for {config.business_name}.

Customer Information:
{review_section}Rating: {rating}
Reviewer Name: {reviewer_name}

Response Objective:
{response_objective}
{client_instructions_section}
Mandatory Grounding Rule (this is the most important instruction in this prompt):
- Your response MUST open by reacting to one specific, concrete detail from the review text - a product, a specific moment, an action, a place in the store, a specific word the customer used. Do not open with a general statement of gratitude or sentiment.
- If there is no review text, ground the response in the rating and business name only - do not invent specifics.
- A response that could be copy-pasted onto a different review with only the name changed has failed this instruction. Before finalizing, check: could this exact sentence apply to a different customer's review? If yes, rewrite it to be specific to this one.

Rating Interpretation:
- 1-2 stars: Acknowledge the customer's feelings briefly, show care, and guide them to contact support for resolution. Be concise - do not write extended apologies or elaborate on the problem. The priority is to move the conversation off the public thread.
- 3 stars: Respond with a balanced, professional, and constructive tone.
- 4-5 stars: Respond with appreciation, grounded in specifics, without generic enthusiasm language.

Handling Mixed Signals:
- Consider both the review text and the star rating to understand the full picture.
- Always lead with what the customer actually wrote - it reflects their experience more directly than the rating alone.
- If the sentiment and rating don't fully align, address the customer's words naturally without calling attention to the mismatch.
{keyword_section}
Content Requirements:
- Address the reviewer by name{" (required)" if config.must_include_reviewer_name else ""} - but do not always open the sentence with the name; vary where it appears.
- Reference the business name naturally{" (required)" if config.must_include_business_name else ", if it fits"}, using a shortened form rather than its full registered name.
- Match the emotional sentiment expressed by the customer.
- Stay in character as the persona above - do not slip into a generic corporate voice.
- Do not invent facts.

Things to Strictly Avoid:
- Do not repeat, restate, or describe the customer's issue in your own words. Acknowledge their feelings without amplifying the specifics of the complaint.
- Do not mention the possibility of similar issues happening in the future. All resolution language applies to the current experience only.
- Do not repeat staff names mentioned in the review, even positively.
- Do not paraphrase the review back to the customer.
- Do not make promises that are not supported by the review context.
- Do not open with "Hi [Name]" followed immediately by "Thank you" or "Thanks for" - vary the opening structure itself, not just the wording.

Response Variety:
- Each response must feel distinct in structure, not just word choice. Vary sentence order, opening move, and where the name/thanks/CTA appear.
- Do not default to predictable patterns like starting with a greeting-then-thanks, or ending with a "look forward to seeing you" style close.
- Write as if this is the only response the customer will ever read from this business - make it feel personal, not templated.
{previous_section}
{tokens_section}
{contact_cta}

Formatting Rules:
- No email addresses in the response unless provided in Business Contact Details above.
- No hashtags or @mentions.
- No excessive exclamation marks.
- Stay within {word_limit} words.
{signature_section}
"""
    return prompt
