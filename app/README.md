# Chwit Travel - Hotel Reservation Web App (prototype)

A working hotel reservation web app for a Mauritius online travel agency,
modeled on the chwit.mu offering (hotels, deals, instant confirmation, 24/7
support). Built with Flask + SQLite, using the repo's 110-hotel Mauritius
inventory (`data/hotels_master.csv`).

## Run it

```bash
pip install flask
python3 app/server.py
# open http://127.0.0.1:5050
```

## What's included

| Page | Route | Features |
|---|---|---|
| Home | `/` | Hero search (district, dates, guests), Today's top deals, Guest favourites |
| Search results | `/search` | Filters: name, district, dates, guests, max price, deals-only; sort by price/rating; per-night + total pricing |
| Hotel detail | `/hotel/<id>` | Star tier, guest rating, promo badge, room-type rate table with promo strikethrough pricing, similar hotels in district |
| Booking | `/book/<id>` | Stay summary, guest details form with validation, POST creates a reservation |
| Confirmation | `/confirmation/<ref>` | Unique `CHW-XXXXXX` reference, full booking recap |
| My bookings | `/bookings` | Look up all reservations by email |

Reservations persist in Postgres when `DATABASE_URL` is set (production),
otherwise in `app/reservations.db` (SQLite, created on first run,
git-ignored).

## Deploying

The repo root has a `render.yaml` blueprint: on [Render](https://render.com),
choose **New -> Blueprint**, select this repo, and Render provisions the web
service plus a managed Postgres database and wires `DATABASE_URL`
automatically. Any Procfile-style host (Railway, Fly.io, Heroku) also works:

```
web: gunicorn --chdir app server:app --bind 0.0.0.0:$PORT
```

To serve it on your own domain, add a custom domain (e.g.
`booking.chwit.mu`) in the host's dashboard and create the CNAME record it
gives you at your registrar.

## Architecture notes

- `app/inventory.py` - inventory layer. Currently derives deterministic
  **demo** rates/ratings/promos from the 110-hotel master list (seeded per
  hotel, stable across restarts). Replace this module with your real
  channel-manager / PMS feed to go live; the rest of the app only consumes
  its dict shape.
- `app/server.py` - routes, reservation storage, date/guest parsing.
- `app/templates/`, `app/static/style.css` - UI. Brand colors are CSS
  variables at the top of `style.css` (`--brand`, `--accent`, ...), so
  re-skinning to the real chwit.mu palette is a one-block edit.

## Known limitations (prototype scope)

- Rates are illustrative, not live inventory (footer on every page says so).
- No payment step, no real confirmation emails, no user accounts/login.
- No flight booking (chwit.mu also sells flights) - hotel-only for now.
- Branding matches the official chwit! logo supplied by the owner: coral
  palette (`--brand: #f8756c` in `static/style.css`), the lowercase
  "chwit!" wordmark with the Esc-key badge as the dot of the i (recreated
  in HTML/CSS in `templates/base.html` using the Baloo 2 rounded font),
  and the "Big World. Bigger You." tagline. If a vector/PNG logo file is
  preferred over the CSS recreation, drop it in `static/` and swap the
  `.logo` markup in `base.html`.
