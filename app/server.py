"""
Travel / hotel reservation web app - Mauritius OTA prototype.

Run:
    python3 app/server.py
Then open http://127.0.0.1:5050

Reservations are stored in Postgres when DATABASE_URL is set (production,
e.g. Render - see render.yaml), otherwise in a local SQLite file. Inventory
comes from data/hotels_master.csv via app/inventory.py (demo rates - swap
for a live channel-manager feed in production).
"""

import datetime
import os
import string
import random
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from sqlalchemy import (Column, Float, Integer, MetaData, String, Table, Text,
                        create_engine, select)

import inventory

APP_DIR = Path(__file__).resolve().parent

app = Flask(__name__)


# ---------------------------------------------------------------------------
# DB - Postgres via DATABASE_URL in production, SQLite locally
# ---------------------------------------------------------------------------
def _database_url():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):  # Render/Heroku style -> SQLAlchemy style
        url = url.replace("postgres://", "postgresql://", 1)
    if url:
        return url
    return f"sqlite:///{os.environ.get('DB_PATH', APP_DIR / 'reservations.db')}"


engine = create_engine(_database_url(), pool_pre_ping=True)
metadata = MetaData()
reservations = Table(
    "reservations", metadata,
    Column("id", Integer, primary_key=True),
    Column("ref", String(20), unique=True, nullable=False),
    Column("hotel_id", Integer, nullable=False),
    Column("hotel_name", Text, nullable=False),
    Column("room_name", Text, nullable=False),
    Column("check_in", String(10), nullable=False),
    Column("check_out", String(10), nullable=False),
    Column("guests", Integer, nullable=False),
    Column("nights", Integer, nullable=False),
    Column("price_per_night", Float, nullable=False),
    Column("total_price", Float, nullable=False),
    Column("promo", Text),
    Column("guest_name", Text, nullable=False),
    Column("guest_email", Text, nullable=False),
    Column("guest_phone", Text),
    Column("created_at", String(25), nullable=False),
)
metadata.create_all(engine)


def new_ref():
    return "CHW-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def parse_dates(args):
    today = datetime.date.today()
    try:
        check_in = datetime.date.fromisoformat(args.get("check_in", ""))
    except ValueError:
        check_in = today + datetime.timedelta(days=14)
    try:
        check_out = datetime.date.fromisoformat(args.get("check_out", ""))
    except ValueError:
        check_out = check_in + datetime.timedelta(days=2)
    if check_out <= check_in:
        check_out = check_in + datetime.timedelta(days=1)
    return check_in, check_out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    featured = sorted(inventory.HOTELS, key=lambda h: h["rating"], reverse=True)[:6]
    deals = [h for h in inventory.HOTELS if h["promo"]]
    deals = sorted(deals, key=lambda h: h["promo_factor"])[:6]
    default_in = datetime.date.today() + datetime.timedelta(days=14)
    return render_template(
        "home.html",
        districts=inventory.DISTRICTS,
        featured=featured,
        deals=deals,
        default_in=default_in.isoformat(),
        default_out=(default_in + datetime.timedelta(days=2)).isoformat(),
    )


@app.route("/search")
def search():
    check_in, check_out = parse_dates(request.args)
    guests = max(1, request.args.get("guests", 2, type=int))
    district = request.args.get("district", "")
    q = request.args.get("q", "").strip().lower()
    max_price = request.args.get("max_price", type=int)
    only_deals = request.args.get("deals") == "1"
    sort = request.args.get("sort", "price")

    results = inventory.HOTELS
    if district:
        results = [h for h in results if h["district"] == district]
    if q:
        results = [h for h in results if q in h["name"].lower()]
    if max_price:
        results = [h for h in results if h["lead_price"] <= max_price]
    if only_deals:
        results = [h for h in results if h["promo"]]

    if sort == "rating":
        results = sorted(results, key=lambda h: h["rating"], reverse=True)
    elif sort == "price_desc":
        results = sorted(results, key=lambda h: h["lead_price"], reverse=True)
    else:
        results = sorted(results, key=lambda h: h["lead_price"])

    nights = (check_out - check_in).days
    return render_template(
        "search.html",
        results=results,
        districts=inventory.DISTRICTS,
        check_in=check_in.isoformat(),
        check_out=check_out.isoformat(),
        nights=nights,
        guests=guests,
        district=district,
        q=request.args.get("q", ""),
        max_price=max_price or "",
        only_deals=only_deals,
        sort=sort,
    )


@app.route("/hotel/<int:hotel_id>")
def hotel_detail(hotel_id):
    hotel = inventory.HOTELS_BY_ID.get(hotel_id)
    if not hotel:
        return render_template("404.html"), 404
    check_in, check_out = parse_dates(request.args)
    nights = (check_out - check_in).days
    guests = max(1, request.args.get("guests", 2, type=int))
    similar = [h for h in inventory.HOTELS
               if h["district"] == hotel["district"] and h["id"] != hotel_id][:4]
    return render_template(
        "hotel.html",
        hotel=hotel,
        check_in=check_in.isoformat(),
        check_out=check_out.isoformat(),
        nights=nights,
        guests=guests,
        similar=similar,
    )


@app.route("/book/<int:hotel_id>", methods=["GET", "POST"])
def book(hotel_id):
    hotel = inventory.HOTELS_BY_ID.get(hotel_id)
    if not hotel:
        return render_template("404.html"), 404
    check_in, check_out = parse_dates(request.values)
    nights = (check_out - check_in).days
    guests = max(1, request.values.get("guests", 2, type=int))
    room_name = request.values.get("room", hotel["rooms"][0]["name"])
    room = next((r for r in hotel["rooms"] if r["name"] == room_name), hotel["rooms"][0])
    price = room["promo_price"] or room["price"]
    total = price * nights

    if request.method == "POST":
        name = request.form.get("guest_name", "").strip()
        email = request.form.get("guest_email", "").strip()
        phone = request.form.get("guest_phone", "").strip()
        errors = []
        if not name:
            errors.append("Please enter the lead guest's full name.")
        if not email or "@" not in email:
            errors.append("Please enter a valid email address for the confirmation.")
        if errors:
            return render_template("book.html", hotel=hotel, room=room, price=price,
                                   total=total, nights=nights, guests=guests,
                                   check_in=check_in.isoformat(), check_out=check_out.isoformat(),
                                   errors=errors, guest_name=name, guest_email=email,
                                   guest_phone=phone)
        with engine.begin() as conn:
            ref = new_ref()
            while conn.execute(select(reservations.c.id)
                               .where(reservations.c.ref == ref)).first():
                ref = new_ref()
            conn.execute(reservations.insert().values(
                ref=ref, hotel_id=hotel_id, hotel_name=hotel["name"],
                room_name=room["name"], check_in=check_in.isoformat(),
                check_out=check_out.isoformat(), guests=guests, nights=nights,
                price_per_night=price, total_price=total, promo=hotel["promo"],
                guest_name=name, guest_email=email, guest_phone=phone,
                created_at=datetime.datetime.now().isoformat(timespec="seconds"),
            ))
        return redirect(url_for("confirmation", ref=ref))

    return render_template("book.html", hotel=hotel, room=room, price=price, total=total,
                           nights=nights, guests=guests, check_in=check_in.isoformat(),
                           check_out=check_out.isoformat(), errors=[],
                           guest_name="", guest_email="", guest_phone="")


@app.route("/confirmation/<ref>")
def confirmation(ref):
    with engine.connect() as conn:
        row = conn.execute(select(reservations)
                           .where(reservations.c.ref == ref)).mappings().first()
    if not row:
        return render_template("404.html"), 404
    return render_template("confirmation.html", r=row)


@app.route("/bookings")
def bookings():
    email = request.args.get("email", "").strip()
    rows = []
    if email:
        with engine.connect() as conn:
            rows = conn.execute(
                select(reservations)
                .where(reservations.c.guest_email == email)
                .order_by(reservations.c.created_at.desc())).mappings().all()
    return render_template("bookings.html", rows=rows, email=email)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5050)),
            debug=False)
