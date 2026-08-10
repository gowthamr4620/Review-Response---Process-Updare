"""The fixed tone vocabulary the prompt builder works with. Descriptions are
shared between two modes:
  - model-selected (default): the model picks the best-fit tone itself
  - locked (opt-in via ReviewDetails.locked_tone): the caller pins a tone,
    typically driven by a business rule such as a rating->tone mapping.
"""

from enum import Enum


class Tone(str, Enum):
    FRIENDLY = "Friendly"
    PROFESSIONAL = "Professional"
    EMPATHETIC = "Empathetic"
    ENTHUSIASTIC = "Enthusiastic"
    CONFIDENT = "Confident"
    CONVERSATIONAL = "Conversational"


TONE_DESCRIPTIONS = {
    Tone.FRIENDLY: (
        'Warm, approachable, and personable, while still speaking as the business ("we"). '
        "Focuses on building a positive connection with the customer."
    ),
    Tone.PROFESSIONAL: (
        "Polished, respectful, and business-appropriate. Clear and confident without sounding "
        "overly formal, robotic, or cold."
    ),
    Tone.EMPATHETIC: (
        "Leads with genuine acknowledgement of the customer's feelings, concerns, or experience "
        "before offering appreciation, explanation, or resolution."
    ),
    Tone.ENTHUSIASTIC: (
        "High-energy, positive, and celebratory. Expresses genuine excitement and appreciation "
        "for exceptional feedback or experiences."
    ),
    Tone.CONFIDENT: (
        "Direct, assured, and authoritative. Demonstrates accountability and expertise without "
        "over-apologizing, hedging, or sounding defensive."
    ),
    Tone.CONVERSATIONAL: (
        'Natural, relaxed, and easy to read rather than a stiff, formal statement, while still '
        'speaking as the business ("we") rather than as an individual.'
    ),
}
