import unittest

from ..core.keyword_matcher import get_top_matching_keywords


class TestGetTopMatchingKeywords(unittest.TestCase):
    def test_empty_review_returns_nothing(self):
        self.assertEqual(get_top_matching_keywords("", ["staff"], 3), [])
        self.assertEqual(get_top_matching_keywords(None, ["staff"], 3), [])

    def test_no_approved_keywords_returns_nothing(self):
        self.assertEqual(get_top_matching_keywords("great staff", None, 3), [])
        self.assertEqual(get_top_matching_keywords("great staff", [], 3), [])

    def test_matches_are_case_insensitive_whole_word(self):
        result = get_top_matching_keywords("The Necklace was Packaged well", ["packaged", "necklace"], 3)
        self.assertEqual(result, ["necklace", "packaged"])

    def test_does_not_match_substrings(self):
        result = get_top_matching_keywords("we helped them", ["help"], 3)
        self.assertEqual(result, [])

    def test_ordered_by_first_appearance_and_capped(self):
        result = get_top_matching_keywords(
            "resizing was fast, packaging was neat, and the necklace is lovely",
            ["necklace", "packaging", "resizing"],
            2,
        )
        self.assertEqual(result, ["resizing", "packaging"])

    def test_unmatched_keywords_are_excluded(self):
        result = get_top_matching_keywords("great service", ["service", "refund"], 3)
        self.assertEqual(result, ["service"])


if __name__ == "__main__":
    unittest.main()
