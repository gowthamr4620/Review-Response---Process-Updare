"""Buckets a star rating into the three feedback bands: Negative (1-2),
Neutral (3), Positive (4-5). Direct port of GetSentimentBand."""

from enum import Enum


class ReviewSentimentBand(str, Enum):
    NEGATIVE = "Negative"
    NEUTRAL = "Neutral"
    POSITIVE = "Positive"


def get_sentiment_band(rating: int) -> ReviewSentimentBand:
    if rating <= 2:
        return ReviewSentimentBand.NEGATIVE
    if rating == 3:
        return ReviewSentimentBand.NEUTRAL
    return ReviewSentimentBand.POSITIVE
