import unittest

from ..urls import clean_url, is_mappls_url, parse_listing_url


class TestParseListingUrl(unittest.TestCase):
    def test_short_link_yields_a_guessed_eloc(self):
        parsed = parse_listing_url("https://mappls.com/2ozc1r")
        self.assertEqual(parsed.eloc, "2OZC1R")
        self.assertEqual(parsed.eloc_confidence, "guess")
        self.assertTrue(parsed.api_ready)

    def test_place_path_yields_an_explicit_eloc(self):
        parsed = parse_listing_url("https://maps.mappls.com/place/ABC123/kalyan-jewellers")
        self.assertEqual(parsed.eloc, "ABC123")
        self.assertEqual(parsed.eloc_confidence, "explicit")

    def test_query_parameter_eloc(self):
        self.assertEqual(parse_listing_url("https://www.mapmyindia.com/s?eloc=xy12z9").eloc, "XY12Z9")

    def test_reserved_segments_are_not_mistaken_for_elocs(self):
        self.assertIsNone(parse_listing_url("https://mappls.com/search").eloc)
        self.assertIsNone(parse_listing_url("https://mappls.com/nearby").eloc)

    def test_viewport_coordinates_are_captured_as_hints(self):
        parsed = parse_listing_url("https://mappls.com/search/atm@28.6139,77.2090,15z")
        self.assertEqual(parsed.kind, "search")
        self.assertAlmostEqual(parsed.hint_latitude, 28.6139)
        self.assertAlmostEqual(parsed.hint_longitude, 77.2090)

    def test_tracking_params_and_fragments_are_dropped(self):
        cleaned = clean_url("https://mappls.com/place/ABC123/x?utm_source=mail&ref=1#map")
        self.assertEqual(cleaned, "https://mappls.com/place/ABC123/x?ref=1")

    def test_host_detection(self):
        self.assertTrue(is_mappls_url("https://brand.mappls.com/stores/delhi"))
        self.assertFalse(is_mappls_url("https://maps.google.com/place/x"))


if __name__ == "__main__":
    unittest.main()
