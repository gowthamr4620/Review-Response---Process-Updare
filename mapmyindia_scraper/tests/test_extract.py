import os
import unittest

from ..extract import extract_listing_from_html, extract_listing_from_json

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        return f.read()


class TestExtractFromHtml(unittest.TestCase):
    def test_jsonld_listing(self):
        listing = extract_listing_from_html(_fixture("listing_jsonld.html"), "https://mappls.com/abc123")
        self.assertEqual(listing.business_name, "Kalyan Jewellers - Connaught Place")
        self.assertEqual(listing.pincode, "110001")
        self.assertAlmostEqual(listing.latitude, 28.6315)
        self.assertAlmostEqual(listing.longitude, 77.2167)
        self.assertEqual(listing.phone, "9876543210")
        self.assertEqual(listing.field_sources["business_name"], "json-ld")

    def test_jsonld_beats_the_og_title(self):
        listing = extract_listing_from_html(_fixture("listing_jsonld.html"), "u")
        self.assertNotEqual(listing.business_name, "Kalyan Jewellers | Connaught Place")

    def test_tel_link_is_captured_as_a_secondary_number(self):
        listing = extract_listing_from_html(_fixture("listing_jsonld.html"), "u")
        self.assertIn("1123456789", listing.phones)

    def test_next_data_app_state(self):
        listing = extract_listing_from_html(_fixture("listing_nextdata.html"), "https://mappls.com/mmi123")
        self.assertEqual(listing.eloc, "MMI123")
        self.assertEqual(listing.business_name, "Muthoot Finance - Kochi Main")
        self.assertEqual(listing.pincode, "682031")
        self.assertEqual(listing.phone, "9812345678")
        self.assertAlmostEqual(listing.latitude, 9.9816)

    def test_empty_page_reports_no_data(self):
        listing = extract_listing_from_html("<html><body>loading</body></html>", "u")
        self.assertFalse(listing.has_any_data)


class TestExtractFromJson(unittest.TestCase):
    def test_mappls_api_shape(self):
        payload = {
            "suggestedLocations": [
                {
                    "eLoc": "MMI999",
                    "placeName": "HDFC Bank ATM",
                    "placeAddress": "Sector 18, Noida",
                    "latitude": 28.5700,
                    "longitude": 77.3210,
                    "addressTokens": {"pincode": "201301", "city": "Noida"},
                    "landlineNo": "0120-4567890",
                }
            ]
        }
        listing = extract_listing_from_json(payload, "u", "mappls-api")
        self.assertEqual(listing.business_name, "HDFC Bank ATM")
        self.assertEqual(listing.pincode, "201301")
        self.assertEqual(listing.phone, "1204567890")
        self.assertEqual(listing.field_sources["address"], "mappls-api")

    def test_pincode_falls_back_to_the_address_text(self):
        payload = {"placeName": "X", "placeAddress": "12 MG Road, Bengaluru 560001"}
        listing = extract_listing_from_json(payload, "u", "mappls-api")
        self.assertEqual(listing.pincode, "560001")
        self.assertEqual(listing.field_sources["pincode"], "address")


if __name__ == "__main__":
    unittest.main()
