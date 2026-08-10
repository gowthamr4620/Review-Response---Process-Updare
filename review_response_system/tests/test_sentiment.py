import unittest

from ..core.sentiment import ReviewSentimentBand, get_sentiment_band


class TestGetSentimentBand(unittest.TestCase):
    def test_negative_band(self):
        self.assertEqual(get_sentiment_band(1), ReviewSentimentBand.NEGATIVE)
        self.assertEqual(get_sentiment_band(2), ReviewSentimentBand.NEGATIVE)

    def test_neutral_band(self):
        self.assertEqual(get_sentiment_band(3), ReviewSentimentBand.NEUTRAL)

    def test_positive_band(self):
        self.assertEqual(get_sentiment_band(4), ReviewSentimentBand.POSITIVE)
        self.assertEqual(get_sentiment_band(5), ReviewSentimentBand.POSITIVE)


if __name__ == "__main__":
    unittest.main()
