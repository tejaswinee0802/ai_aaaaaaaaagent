"""
Configuration for the Hotel Revenue Management Pricing Agent.

Edit this file to:
  - refresh FX_TO_EUR rates before each data-collection round
  - change the 3 sampled shop dates (or regenerate with pick_random_dates)
  - tune PROMO_KEYWORDS / PARTNER_KEYWORDS used to classify rows
"""

import calendar
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates"
OUTPUT_DIR = ROOT_DIR / "output"

HOTELS_MASTER_CSV = DATA_DIR / "hotels_master.csv"
PRICE_TEMPLATE_XLSX = TEMPLATES_DIR / "price_input_template.xlsx"

# ---------------------------------------------------------------------------
# Shop dates
# ---------------------------------------------------------------------------
# One random check-in date per month was drawn for this round (seed: current
# session run on 2026-07-14). Re-run pick_random_dates() for a fresh round.
SHOP_DATES = [
    {"date": "2026-08-01", "weekday": "Saturday", "month": "August"},
    {"date": "2026-09-05", "weekday": "Saturday", "month": "September"},
    {"date": "2026-10-07", "weekday": "Wednesday", "month": "October"},
]
LOS_NIGHTS = 2  # length of stay used for every shop (2 adults, 1 room, no meal plan bias)


def pick_random_dates(year: int = 2026):
    """Draw one fresh random date in each of Aug/Sep/Oct of `year`."""
    dates = []
    for month, name in ((8, "August"), (9, "September"), (10, "October")):
        last_day = calendar.monthrange(year, month)[1]
        day = random.randint(1, last_day)
        import datetime

        d = datetime.date(year, month, day)
        dates.append({"date": d.isoformat(), "weekday": d.strftime("%A"), "month": name})
    return dates


# ---------------------------------------------------------------------------
# FX rates -> EUR (multiply a price in that currency by the factor to get EUR)
# Snapshot taken 2026-07-14 from ECB reference rates / Bank of Mauritius.
# REFRESH THESE before each real data-collection round - FX moves daily.
# ---------------------------------------------------------------------------
FX_TO_EUR = {
    "EUR": 1.0,
    "USD": 1 / 1.1400,   # ECB EUR/USD ~1.14
    "GBP": 1 / 0.8525,   # ECB EUR/GBP ~0.8525
    "MUR": 1 / 53.70,    # Bank of Mauritius EUR/MUR ~53.70
    "ZAR": 1 / 18.63,    # ECB EUR/ZAR ~18.63
}
FX_SNAPSHOT_DATE = "2026-07-14"

# ---------------------------------------------------------------------------
# Sources & inventory filtering
# ---------------------------------------------------------------------------
SOURCE_BOOKING = "Booking.com"
SOURCE_OWN_SITE = "Hotel Own Website"
VALID_SOURCES = [SOURCE_BOOKING, SOURCE_OWN_SITE]

# On Booking.com, "Sold By" tells you whether the rate is the hotel's own
# Booking.com inventory or a reseller/partner/wholesaler rate injected into
# the search results. Per the brief we ONLY keep "Booking.com" (direct
# property inventory) rows for the Booking.com source; partner/third-party
# rows are excluded from all analysis.
SOLD_BY_DIRECT = "Booking.com"
SOLD_BY_PARTNER = "Partner / Third-Party"
VALID_SOLD_BY = [SOLD_BY_DIRECT, SOLD_BY_PARTNER]

# ---------------------------------------------------------------------------
# Promotion / special-offer detection
# ---------------------------------------------------------------------------
# Case-insensitive substring match against the "Rate Plan / Offer Label"
# column filled in during data collection (e.g. what's printed on the rate
# on Booking.com: "Genius Discount", "Mobile Rate", or on a hotel's own site:
# "Early Bird -15%", "Book Direct Best Rate").
PROMO_KEYWORDS = [
    "genius", "mobile rate", "mobile-only", "early bird", "early booking",
    "last minute", "flash sale", "member", "loyalty", "discount", "%",
    "free night", "free cancellation deal", "book direct", "special offer",
    "promo", "deal", "black friday", "cyber", "honeymoon offer",
    "long stay", "advance purchase", "non-refundable rate",
]

CURRENCIES = ["EUR", "USD", "GBP", "MUR", "ZAR"]
