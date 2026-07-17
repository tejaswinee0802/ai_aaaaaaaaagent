"""
Inventory layer for the reservation app.

Loads the 110-hotel Mauritius competitive set from data/hotels_master.csv and
derives a deterministic demo inventory for each hotel: star tier, guest
rating, nightly base rate, room types and running promotions. Deterministic
(seeded per hotel id) so pages are stable across restarts without a database
of real rates. Swap this module for a real CMS/channel-manager feed when the
site goes live.
"""

import csv
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOTELS_CSV = ROOT / "data" / "hotels_master.csv"

TIERS = [
    # (star label, weight, base rate EUR range/night)
    ("5-star Luxury", 0.25, (420, 950)),
    ("4-star Superior", 0.35, (180, 420)),
    ("3-star Comfort", 0.30, (75, 180)),
    ("Boutique / Guesthouse", 0.10, (55, 120)),
]

ROOM_TYPES = [
    ("Standard Double or Twin Room", 1.00),
    ("Superior Sea View Room", 1.35),
    ("Deluxe Suite", 1.90),
    ("Family Room (2 Adults + 2 Children)", 1.55),
]

PROMOS = [
    ("Early Bird -15%", 0.85),
    ("Last Minute Deal -12%", 0.88),
    ("Member Price -10%", 0.90),
    ("Free Night: Stay 4 Pay 3", 0.75),
    ("Honeymoon Offer -20%", 0.80),
]

DISTRICT_BLURB = {
    "Black River": "West coast sunsets, Le Morne lagoon and world-class kitesurfing.",
    "Flacq": "East coast powder-white beaches and turquoise Belle Mare lagoon.",
    "Grand Port": "Historic south-east, minutes from the airport and Blue Bay marine park.",
    "Grand Baie": "The island's liveliest beach town - shopping, dining and nightlife.",
    "Moka": "Cool central highlands, business hub and Bagatelle mall.",
    "Pamplemousses": "North coast beaches near Grand Baie and the famous botanical garden.",
    "Plaine Wilhems": "Urban comfort in the island's residential heart.",
    "Port Louis": "Capital city waterfront - markets, museums and the Caudan.",
    "Rivière du Rempart": "Northern tip - Grand Gaube lagoons and offshore islands.",
    "Savanne": "Wild south coast - cliffs, rum distilleries and Bel Ombre golf.",
}


def _tier_for(rng: random.Random, name: str):
    lux_markers = ("LUX", "Four Seasons", "One&Only", "St Regis", "Shangri-La", "Oberoi",
                    "Royal Palm", "Constance", "Maradiva", "JW Marriott", "Sofitel",
                    "InterContinental", "Westin", "Hilton", "Anantara", "Le Méridien",
                    "Radisson", "Outrigger", "Heritage", "Shanti", "Beachcomber", "Club Med",
                    "RIU", "Salt of Palmar", "Le Touessrok", "Saint Géran")
    if any(m.lower() in name.lower() for m in lux_markers):
        return TIERS[0] if rng.random() < 0.7 else TIERS[1]
    r = rng.random()
    acc = 0.0
    for tier in TIERS:
        acc += tier[1]
        if r <= acc:
            return tier
    return TIERS[-1]


def load_inventory():
    hotels = []
    with open(HOTELS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            hid = int(row["HotelID"])
            rng = random.Random(hid * 7919)  # deterministic per hotel
            star, _, (lo, hi) = _tier_for(rng, row["HotelName"])
            base = round(rng.uniform(lo, hi))
            rating = round(rng.uniform(7.2, 9.6), 1)
            reviews = rng.randint(120, 5200)
            promo = None
            if rng.random() < 0.4:
                promo = rng.choice(PROMOS)
            rooms = []
            for rname, mult in ROOM_TYPES:
                if mult > 1.5 and star.startswith("Boutique"):
                    continue
                price = round(base * mult)
                rooms.append({
                    "name": rname,
                    "price": price,
                    "promo_price": round(price * promo[1]) if promo else None,
                })
            hotels.append({
                "id": hid,
                "name": row["HotelName"],
                "district": row["District"],
                "blurb": DISTRICT_BLURB.get(row["District"], ""),
                "star": star,
                "rating": rating,
                "reviews": reviews,
                "base_price": base,
                "promo": promo[0] if promo else None,
                "promo_factor": promo[1] if promo else 1.0,
                "rooms": rooms,
                "lead_price": rooms[0]["promo_price"] or rooms[0]["price"],
            })
    return hotels


HOTELS = load_inventory()
HOTELS_BY_ID = {h["id"]: h for h in HOTELS}
DISTRICTS = sorted({h["district"] for h in HOTELS})
