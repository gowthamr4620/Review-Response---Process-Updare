import unittest

from ..normalize import (
    haversine_metres,
    is_subset_match,
    normalize_address,
    normalize_name,
    normalize_phone,
    normalize_pincode,
    phone_digits_match,
    similarity,
)


class TestNormalisers(unittest.TestCase):
    def test_legal_suffixes_do_not_affect_the_name(self):
        self.assertEqual(normalize_name("Kalyan Jewellers Pvt. Ltd."), normalize_name("Kalyan Jewellers"))

    def test_address_abbreviations_are_expanded(self):
        self.assertEqual(
            normalize_address("Shop No. 5, Gr Flr, M.G. Rd, Opp Metro, Bengaluru - 560001"),
            "shop 5 ground floor mg road opposite metro bengaluru",
        )

    def test_pincode_survives_excel_float_formatting(self):
        self.assertEqual(normalize_pincode(560001.0), "560001")
        self.assertEqual(normalize_pincode("Bengaluru - 560001, India"), "560001")
        self.assertIsNone(normalize_pincode("56001"))

    def test_phone_forms_reduce_to_the_same_ten_digits(self):
        for value in ("+91 98765-43210", "0091 9876543210", "09876543210", 9876543210.0):
            self.assertEqual(normalize_phone(value), "9876543210", value)
        self.assertTrue(phone_digits_match("+91 98765 43210", "9876543210"))
        self.assertFalse(phone_digits_match("9876543210", "9876543211"))

    def test_similarity_is_order_insensitive(self):
        a = normalize_address("MG Road, Bengaluru")
        b = normalize_address("Bengaluru, M.G. Rd")
        self.assertGreaterEqual(similarity(a, b), 0.85)

    def test_subset_match_detects_a_shortened_address(self):
        self.assertTrue(is_subset_match("mg road bengaluru", "shop 5 mg road bengaluru karnataka"))
        self.assertFalse(is_subset_match("mg road bengaluru", "brigade road mumbai"))

    def test_haversine_is_metres(self):
        self.assertAlmostEqual(haversine_metres(28.6139, 77.2090, 28.6139, 77.2090), 0.0)
        self.assertLess(haversine_metres(28.6139, 77.2090, 28.6145, 77.2095), 120)


if __name__ == "__main__":
    unittest.main()
