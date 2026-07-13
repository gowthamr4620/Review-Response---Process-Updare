"""
Client configuration for all 6 brands. This is a stand-in for what will
eventually be DB rows - one ClientReviewResponseConfig per client, plus
the path to that client's review export file.

tone must be one of: ClientTone.ENTHUSIASTIC, FRIENDLY, CONVERSATIONAL,
                      EMPATHETIC, CONFIDENT, PROFESSIONAL
length must be one of: ClientLength.CONCISE, DEFAULT, ELABORATE

custom_instructions: content/phrasing guidance only (what to mention, what
tone of resolution to offer, what NOT to discuss) - never repetition/word
control, that's platform-owned and already handled in build_prompt.py.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from client_config_schema import ClientReviewResponseConfig, ClientTone, ClientLength

CLIENTS = {

    "muthoot_finance": {
        "config": ClientReviewResponseConfig(
            client_id="muthoot_finance",
            business_name="Muthoot Finance",
            tone=ClientTone.ENTHUSIASTIC,
            length=ClientLength.DEFAULT,
            custom_instructions=None,
            contact_number="011 4669 7754",
            support_email=None,
            website_url=None,
            signature=None,
            brand_keywords=None,
        ),
        "reviews_file": "data/muthoot_finance_reviews.csv",
    },

    "muthoot_fincorp": {
        "config": ClientReviewResponseConfig(
            client_id="muthoot_fincorp",
            business_name="Muthoot Fincorp",
            tone=ClientTone.EMPATHETIC,
            length=ClientLength.CONCISE,
            custom_instructions=None,
            contact_number="1800 102 1616",
            support_email="customercare@muthoot.com",
            website_url=None,
            signature=None,
            brand_keywords=None,
        ),
        "reviews_file": "data/muthoot_fincorp_reviews.csv",
    },

    "decathlon": {
        "config": ClientReviewResponseConfig(
            client_id="decathlon",
            business_name="Decathlon",
            tone=ClientTone.FRIENDLY,
            length=ClientLength.ELABORATE,
            custom_instructions=None,
            contact_number="7676798989",
            support_email="care.india@decathlon.com",
            website_url=None,
            signature=None,
            brand_keywords=[
                "Cycle", "Kids scooter", "Swimwear", "Swimming goggles",
                "Swimming caps", "Towels", "Badminton rackets", "Tennis rackets",
                "Padel rackets", "Pickleball rackets", "Jackets", "Thermals",
                "Rain coat", "Cricket bat", "Yoga mat", "Track pants", "Tents",
                "T-shirts", "Shorts", "Shoes", "Puffer jacket", "Leather jacket",
                "Sweaters", "Fleece jacket", "Winter cap", "Neck warmer",
                "Hoodies", "Gloves",
            ],
        ),
        "reviews_file": "data/decathlon_reviews.csv",
    },

    "forevermark": {
        "config": ClientReviewResponseConfig(
            client_id="forevermark",
            business_name="Forevermark",
            tone=ClientTone.CONFIDENT,
            length=ClientLength.DEFAULT,
            custom_instructions=None,
            contact_number="1800 210 2121",
            support_email="customercare@forevermark.com",
            website_url=None,
            signature=None,
            brand_keywords=None,
        ),
        "reviews_file": "data/forevermark_reviews.csv",
    },

    "candere": {
        "config": ClientReviewResponseConfig(
            client_id="candere",
            business_name="Candere",
            tone=ClientTone.CONVERSATIONAL,
            length=ClientLength.CONCISE,
            custom_instructions=(
                "Do not repeat staff names in the response, even if they are mentioned by the reviewer. "
                "For low-rated/negative reviews (1-3 stars), encourage the customer to contact Customer Care "
                "as early as possible in the response. Keep the acknowledgment brief, instead of providing "
                "lengthy explanations. "
                "Do not restate or describe the customer's complaint in responses to negative reviews. "
                "Acknowledge the customer's experience and emotions with empathy, but avoid repeating the "
                "issue, as it reinforces negative associations in a public forum. "
                "Focus on resolution rather than the problem. Express a commitment to helping resolve the "
                "current concern without discussing the possibility of similar issues occurring in the future "
                "or making references to preventing future incidents."
            ),
            contact_number="2261066262",
            support_email="support@candere.com",
            website_url=None,
            signature="Regards, Candere - A Kalyan Company",
            brand_keywords=None,
        ),
        "reviews_file": "data/candere_reviews.csv",
    },

    "grt": {
        "config": ClientReviewResponseConfig(
            client_id="grt",
            business_name="GRT Jewellers",
            tone=ClientTone.PROFESSIONAL,
            length=ClientLength.DEFAULT,
            custom_instructions=None,
            contact_number="1800 203 1000",
            support_email="mail@grtjewels.com",
            website_url=None,
            signature="Best, GRT Jewellers",
            brand_keywords=None,
        ),
        "reviews_file": "data/grt_reviews.csv",
    },

}
