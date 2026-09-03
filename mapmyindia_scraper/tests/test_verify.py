import unittest

from ..models import Listing, Verdict
from ..verify import VerifyConfig, verify_listing


def _listing(**kwargs):
    base = dict(
        source_url="https://mappls.com/abc123",
        business_name="Kalyan Jewellers - Connaught Place",
        address="Shop 5, Block A, Connaught Place, New Delhi",
        pincode="110001",
        latitude=28.6315,
        longitude=77.2167,
        phones=["9876543210"],
    )
    base.update(kwargs)
    return Listing(**base)


def _expected(**kwargs):
    base = dict(
        business_name="Kalyan Jewellers Connaught Place",
        address="Shop No 5, Blk A, Connaught Pl, New Delhi - 110001",
        pincode="110001",
        latitude=28.6315,
        longitude=77.2167,
        phone="+91 98765 43210",
    )
    base.update(kwargs)
    return base


class TestVerifyListing(unittest.TestCase):
    def test_clean_row_matches_across_all_five_fields(self):
        result = verify_listing(2, _expected(), _listing())
        for name, comparison in result.comparisons.items():
            self.assertEqual(comparison.verdict, Verdict.MATCH, f"{name}: {comparison}")
        self.assertEqual(result.row_verdict, "MATCH")

    def test_absent_field_on_mappls_is_not_a_mismatch(self):
        result = verify_listing(2, _expected(), _listing(phones=[]))
        self.assertEqual(result.comparisons["phone"].verdict, Verdict.MISSING_ON_MAPPLS)
        self.assertEqual(result.row_verdict, "INCOMPLETE")

    def test_value_the_client_did_not_share_is_flagged_separately(self):
        result = verify_listing(2, _expected(phone=None), _listing())
        self.assertEqual(result.comparisons["phone"].verdict, Verdict.MISSING_IN_SHEET)

    def test_wrong_pincode_is_a_mismatch(self):
        result = verify_listing(2, _expected(pincode="110020"), _listing())
        self.assertEqual(result.comparisons["pincode"].verdict, Verdict.MISMATCH)
        self.assertEqual(result.row_verdict, "MISMATCH")

    def test_coordinates_within_tolerance_match(self):
        result = verify_listing(2, _expected(latitude=28.63155, longitude=77.21675), _listing())
        self.assertEqual(result.comparisons["latitude"].verdict, Verdict.MATCH)
        self.assertLess(result.comparisons["latitude"].score, 100)

    def test_coordinates_a_few_hundred_metres_out_go_to_review(self):
        result = verify_listing(2, _expected(latitude=28.6340, longitude=77.2167), _listing())
        self.assertEqual(result.comparisons["latitude"].verdict, Verdict.NEAR_MATCH)
        self.assertEqual(result.row_verdict, "REVIEW")

    def test_swapped_coordinates_are_called_out_by_name(self):
        result = verify_listing(2, _expected(latitude=77.2167, longitude=28.6315), _listing())
        comparison = result.comparisons["latitude"]
        self.assertEqual(comparison.verdict, Verdict.MISMATCH)
        self.assertIn("swapped", comparison.note)

    def test_a_secondary_number_on_the_listing_still_counts_as_a_match(self):
        listing = _listing(phones=["1123456789", "9876543210"])
        result = verify_listing(2, _expected(), listing)
        self.assertEqual(result.comparisons["phone"].verdict, Verdict.MATCH)
        self.assertIn("secondary", result.comparisons["phone"].note)

    def test_different_branch_of_the_same_brand_is_a_name_mismatch(self):
        result = verify_listing(2, _expected(business_name="Tanishq Jewellers Karol Bagh"), _listing())
        self.assertEqual(result.comparisons["business_name"].verdict, Verdict.MISMATCH)

    def test_fetch_failure_does_not_manufacture_mismatches(self):
        listing = _listing(error="HTTP 404 fetching listing")
        result = verify_listing(2, _expected(), listing)
        self.assertEqual(result.row_verdict, "FETCH ERROR")
        self.assertFalse(any(c.verdict == Verdict.MISMATCH for c in result.comparisons.values()))

    def test_thresholds_are_configurable(self):
        strict = VerifyConfig(geo_tolerance_m=1.0, geo_review_m=2.0)
        result = verify_listing(2, _expected(latitude=28.6320), _listing(), strict)
        self.assertEqual(result.comparisons["latitude"].verdict, Verdict.MISMATCH)


if __name__ == "__main__":
    unittest.main()
