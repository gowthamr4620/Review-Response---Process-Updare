"""
Variant WITH Grounding Instruction added, otherwise identical to
build_prompt_corrected.py's build_prompt_locked_tone. This isolates the one
variable under test: does adding the grounding instruction measurably reduce
repetition versus persona-only, holding everything else constant (tone,
length, signature, client instructions, keywords, contact info)?
"""

from build_prompt_corrected import TONE_PERSONAS, _contact_cta


def build_prompt_locked_tone_with_grounding(
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

    # --- The ONE addition under test vs. the persona-only variant ---
    grounding_block = """
Grounding Instruction:
Open by reacting to one specific, concrete detail from the review text (a product, a moment, a specific word used) rather than a general statement of gratitude or apology. If there is no review text, respond based on the rating only, without inventing specifics.
"""

    prompt = f"""{persona}
{client_instructions_block}
Customer Information:
Review Text: {review_text}
Rating: {rating}
Reviewer Name: {reviewer_name}
{grounding_block}
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
