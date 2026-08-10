"""
Data model for the four upload categories the system takes in:
Business Info, Review Details, Keywords, and Signature & Customer Support
Details. These map directly onto the fields the prompt builder
(core/prompt_builder.py) consumes — see that module for how each field is
used structurally, mirroring the reference C# PrepareOpenAIReviewRequest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class AIResponseLengthType(str, Enum):
    CONCISE = "Concise"
    DEFAULT = "Default"
    ELABORATE = "Elaborate"


@dataclass
class BusinessInfo:
    """Uploaded once per business; identifies who the response speaks for."""
    business_name: str


@dataclass
class ReviewDetails:
    """The review being responded to."""
    reviewer_name: str
    rating: int
    review: Optional[str] = None
    ai_response_length_type: AIResponseLengthType = AIResponseLengthType.DEFAULT

    def __post_init__(self) -> None:
        if not 1 <= self.rating <= 5:
            raise ValueError(f"rating must be between 1 and 5, got {self.rating}")

    @property
    def review_text_exists(self) -> bool:
        return bool(self.review and self.review.strip())


@dataclass
class Keywords:
    """
    Pre-approved vocabulary for this business/category. The prompt builder
    never lets the model free-extract keywords from the review — it only
    ever sees words from this list that are also deterministically confirmed
    present in the review text (see core/keyword_matcher.py).
    """
    approved_keywords: List[str] = field(default_factory=list)


@dataclass
class SignatureSupportDetails:
    """Signature and support contact info to weave into/append to the response."""
    signature: Optional[str] = None
    contact_number: Optional[str] = None
    support_email: Optional[str] = None
    website_url: Optional[str] = None

    def as_tokens_line(self) -> str:
        """Renders populated contact fields as the 'tokens' string the prompt
        instructs the model to include inside the response body."""
        parts = []
        if self.contact_number:
            parts.append(f"Contact Number: {self.contact_number}")
        if self.support_email:
            parts.append(f"Support Email: {self.support_email}")
        if self.website_url:
            parts.append(f"Website: {self.website_url}")
        return ", ".join(parts)


@dataclass
class ReviewResponseRequest:
    """Bundles the four uploaded inputs into one request for the builder."""
    business_info: BusinessInfo
    review_details: ReviewDetails
    keywords: Keywords = field(default_factory=Keywords)
    support_details: SignatureSupportDetails = field(default_factory=SignatureSupportDetails)
