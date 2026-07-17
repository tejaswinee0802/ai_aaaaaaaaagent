"""
Travel / hotel reservation web app - Mauritius OTA prototype.

Run:
    python3 app/server.py
Then open http://127.0.0.1:5050

Reservations are stored in app/reservations.db (SQLite). Inventory comes
from data/hotels_master.csv via app/inventory.py (demo rates - swap for a
live channel-manager feed in production).
"""

import datetime
import os
import sqlite3
import string
import random
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for

import inventory

APP_DIR = Path(__file__).resolve().parent
# Set DB_PATH env var in production to a persistent-disk location, otherwise
# the SQLite file sits next to the code (fine locally; on platforms with
# ephemeral filesystems it is wiped on every redeploy).
DB_PATH = Path(os.environ.get("DB_PATH", APP_DIR / "reservations.db"))

app = Flask(__name__)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT UNIQUE NOT NULL,
                hotel_id INTEGER NOT NULL,
                hotel_name TEXT NOT NULL,
                room_name TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                guests INTEGER NOT NULL,
                nights INTEGER NOT NULL,
                price_per_night REAL NOT NULL,
                total_price REAL NOT NULL,
                promo TEXT,
                guest_name TEXT NOT NULL,
                guest_email TEXT NOT NULL,
                guest_phone TEXT,
                created_at TEXT NOT NULL
            )
        """)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


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
        db = get_db()
        ref = new_ref()
        while db.execute("SELECT 1 FROM reservations WHERE ref=?", (ref,)).fetchone():
            ref = new_ref()
        db.execute(
            """INSERT INTO reservations
               (ref, hotel_id, hotel_name, room_name, check_in, check_out, guests,
                nights, price_per_night, total_price, promo, guest_name, guest_email,
                guest_phone, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ref, hotel_id, hotel["name"], room["name"], check_in.isoformat(),
             check_out.isoformat(), guests, nights, price, total, hotel["promo"],
             name, email, phone, datetime.datetime.now().isoformat(timespec="seconds")),
        )
        db.commit()
        return redirect(url_for("confirmation", ref=ref))

    return render_template("book.html", hotel=hotel, room=room, price=price, total=total,
                           nights=nights, guests=guests, check_in=check_in.isoformat(),
                           check_out=check_out.isoformat(), errors=[],
                           guest_name="", guest_email="", guest_phone="")


@app.route("/confirmation/<ref>")
def confirmation(ref):
    row = get_db().execute("SELECT * FROM reservations WHERE ref=?", (ref,)).fetchone()
    if not row:
        return render_template("404.html"), 404
    return render_template("confirmation.html", r=row)


@app.route("/bookings")
def bookings():
    email = request.args.get("email", "").strip()
    rows = []
    if email:
        rows = get_db().execute(
            "SELECT * FROM reservations WHERE guest_email=? ORDER BY created_at DESC",
            (email,)).fetchall()
    return render_template("bookings.html", rows=rows, email=email)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 5050)),
            debug=False)
