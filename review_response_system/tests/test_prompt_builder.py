import unittest

from ..core.models import (
    AIResponseLengthType,
    BusinessInfo,
    Keywords,
    ReviewDetails,
    ReviewResponseRequest,
    SignatureSupportDetails,
)
from ..core.prompt_builder import build_review_response_prompt
from ..core.tone import Tone


def _make_request(**review_overrides) -> ReviewResponseRequest:
    review_defaults = dict(
        reviewer_name="Priya",
        rating=5,
        review="The necklace was beautifully packaged.",
        ai_response_length_type=AIResponseLengthType.DEFAULT,
    )
    review_defaults.update(review_overrides)
    return ReviewResponseRequest(
        business_info=BusinessInfo(business_name="Candere"),
        review_details=ReviewDetails(**review_defaults),
        keywords=Keywords(approved_keywords=["necklace", "packaged"]),
        support_details=SignatureSupportDetails(
            signature="Regards, Candere",
            contact_number="123456",
            support_email="support@candere.com",
        ),
    )


class TestBuildReviewResponsePrompt(unittest.TestCase):
    def test_voice_instruction_forbids_singular_first_person(self):
        chat_request = build_review_response_prompt(_make_request())
        self.assertIn('Never use "I"', chat_request.prompt)
        self.assertIn("first-person plural only", chat_request.prompt)

    def test_guardrails_present(self):
        chat_request = build_review_response_prompt(_make_request())
        self.assertIn("Do not name any staff member", chat_request.prompt)
        self.assertIn("Do not paraphrase or summarize the review's content", chat_request.prompt)

    def test_positive_review_includes_matched_keywords(self):
        chat_request = build_review_response_prompt(_make_request(rating=5))
        self.assertIn("necklace, packaged", chat_request.prompt)

    def test_negative_review_never_includes_keywords(self):
        chat_request = build_review_response_prompt(_make_request(
            rating=1, review="The necklace arrived packaged but broken."
        ))
        self.assertIn("No approved keywords", chat_request.prompt)
        self.assertNotIn("You may use this approved keyword", chat_request.prompt)

    def test_no_review_text_falls_back_to_rating_only_section(self):
        chat_request = build_review_response_prompt(_make_request(review=None, rating=4))
        self.assertNotIn("Review Text:", chat_request.prompt)
        self.assertIn("Rating: 4", chat_request.prompt)

    def test_length_settings_scale_with_type(self):
        concise = build_review_response_prompt(_make_request(ai_response_length_type=AIResponseLengthType.CONCISE))
        elaborate = build_review_response_prompt(_make_request(ai_response_length_type=AIResponseLengthType.ELABORATE))
        self.assertEqual(concise.max_tokens, 70)
        self.assertEqual(elaborate.max_tokens, 200)
        self.assertIn("50 words", concise.prompt)
        self.assertIn("150 words", elaborate.prompt)

    def test_support_details_included(self):
        chat_request = build_review_response_prompt(_make_request())
        self.assertIn("Contact Number: 123456", chat_request.prompt)
        self.assertIn("Support Email: support@candere.com", chat_request.prompt)
        self.assertIn("Regards, Candere", chat_request.prompt)

    def test_omits_support_details_when_absent(self):
        request = _make_request()
        request.support_details = SignatureSupportDetails()
        chat_request = build_review_response_prompt(request)
        self.assertNotIn("Include ", chat_request.prompt)

    def test_locked_tone_replaces_model_selected_tone_instruction(self):
        chat_request = build_review_response_prompt(_make_request(locked_tone=Tone.EMPATHETIC, rating=1))
        self.assertIn("has already been selected for this review", chat_request.prompt)
        self.assertIn("Empathetic:", chat_request.prompt)
        self.assertNotIn("Select the most appropriate tone", chat_request.prompt)

    def test_default_tone_instruction_lets_model_choose(self):
        chat_request = build_review_response_prompt(_make_request())
        self.assertIn("Select the most appropriate tone", chat_request.prompt)


if __name__ == "__main__":
    unittest.main()
