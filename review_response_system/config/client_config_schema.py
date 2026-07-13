"""
Client configuration - corrected scope.

Client-controllable (via account/admin panel):
  - tone: one of a FIXED predefined list (not freeform)
  - length: one of a FIXED predefined list
  - custom_instructions: freeform prose describing HOW to respond / phrase
    things (e.g. "always mention our 1-year warranty for jewellery",
    "never discuss pricing in responses") - NOT stopwords, NOT repetition
    control. This is about response content/behavior, not word banning.
  - appended fields: reviewer name, business name, contact number,
    support email - structural, not prose.

Platform-owned, invisible to clients, never exposed for editing:
  - banned/rotated word lists
  - tone instruction pool variants (client picks "Enthusiastic", platform
    decides HOW that's phrased across many calls)
  - grounding/anti-templating mechanics
  - deterministic variety selection
"""

from dataclasses import dataclass, field
from enum import Enum


class ClientTone(str, Enum):
    ENTHUSIASTIC = "Enthusiastic"
    FRIENDLY = "Friendly"
    CONVERSATIONAL = "Conversational"
    EMPATHETIC = "Empathetic"
    CONFIDENT = "Confident"
    PROFESSIONAL = "Professional"


class ClientLength(str, Enum):
    CONCISE = "Concise"
    DEFAULT = "Default"
    ELABORATE = "Elaborate"


LENGTH_WORD_LIMITS = {
    ClientLength.CONCISE: 50,
    ClientLength.DEFAULT: 80,
    ClientLength.ELABORATE: 120,
}


@dataclass
class ClientReviewResponseConfig:
    client_id: str
    business_name: str

    # --- Client-controlled: pick from fixed lists only ---
    tone: ClientTone = ClientTone.PROFESSIONAL
    length: ClientLength = ClientLength.DEFAULT

    # --- Client-controlled: freeform, but scoped to response STYLE/CONTENT
    # rules only ("how to respond, how to phrase"), never repetition control.
    custom_instructions: str | None = None

    # --- Client-controlled: structured fields to append ---
    must_include_reviewer_name: bool = True
    must_include_business_name: bool = True
    contact_number: str | None = None
    support_email: str | None = None
    website_url: str | None = None
    signature: str | None = None
    brand_keywords: list[str] | None = None


def validate_custom_instructions(text: str) -> tuple[bool, str | None]:
    """
    Guardrail for client-supplied freeform instructions before they're saved.
    Clients don't control repetition/stopwords at all, so the risks here are:
    (1) instructions trying to override platform safety rules, and
    (2) instructions that would themselves reintroduce repetition by forcing
        identical phrasing across every response.
    Production version should use a real classifier. Sketch only.
    """
    lowered = text.lower()
    override_flags = ["ignore previous", "ignore the above", "disregard the rules",
                       "invent", "promise a refund", "guarantee"]
    for flag in override_flags:
        if flag in lowered:
            return False, f"Instruction contains disallowed override pattern: '{flag}'"

    repetition_risk_flags = ["always start with", "always use the phrase", "always say",
                              "every response should begin with"]
    for flag in repetition_risk_flags:
        if flag in lowered:
            return False, (
                f"Instruction pattern '{flag}' would force identical phrasing across "
                "all responses, which conflicts with platform anti-repetition rules. "
                "Consider rephrasing as a content requirement rather than a fixed phrase."
            )
    return True, None
