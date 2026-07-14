"""
Generates the manual data-collection workbook: templates/price_input_template.xlsx

Usage:
    python3 src/generate_template.py

Produces 3 sheets:
  1. Instructions          - how to fill it in, what counts as a valid row
  2. Hotels Reference       - one row per hotel, fill in guest rating / star
                              category once (not per date)
  3. Price Data Entry       - one row per (hotel x source x shop date),
                              pre-populated with hotel/date, blank price cells
                              for the person collecting prices to fill in
"""

import csv

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import config

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")


def load_hotels():
    with open(config.HOTELS_MASTER_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def style_header(ws, row=1):
    for cell in ws[row]:
        if cell.value:
            cell.fill = HEADER_FILL
            cell.font = HEADER_FONT
            cell.alignment = Alignment(vertical="center", wrap_text=True)


def build_instructions(wb):
    ws = wb.active
    ws.title = "Instructions"
    ws.column_dimensions["A"].width = 100
    lines = [
        ("Hotel Revenue Management - Competitive Pricing Data Collection", True),
        ("", False),
        ("PURPOSE", True),
        ("Collect comparable room rates for the Black River / Flacq / Grand Port / etc. "
         "Mauritius competitive set from Booking.com and each hotel's own website, so the "
         "analysis engine can build a EUR-normalised, promotion-flagged pricing comparison.", False),
        ("", False),
        ("WHAT TO FILL IN - go to the 'Price Data Entry' sheet", True),
        ("Every row is pre-filled with HotelID / HotelName / Source / CheckInDate / Nights. "
         "For each row, fill in the yellow columns only:", False),
        ("  - RoomType: the cheapest bookable room/category shown (e.g. 'Standard Double or Twin Room')", False),
        ("  - RatePlanOfferLabel: copy the exact label shown on the rate (e.g. 'Genius Discount', "
         "'Mobile Rate', 'Early Bird -15%', 'Standard Rate', 'Book Direct Rate'). Leave as 'Standard Rate' "
         "if no promo/label is shown.", False),
        ("  - Price: the total price for the stay (or per-night price - just be CONSISTENT for every row you fill), "
         "as displayed, before you convert anything. Use the currency actually shown.", False),
        ("  - Currency: EUR / USD / GBP / MUR / ZAR - whatever currency the price was displayed in.", False),
        ("  - SoldBy (Booking.com rows ONLY): choose 'Booking.com' if the rate is the property's own "
         "Booking.com inventory (standard listing), or 'Partner / Third-Party' if Booking.com shows it as "
         "supplied by a reseller/wholesaler partner. THIRD-PARTY / PARTNER ROWS ARE EXCLUDED FROM THE ANALYSIS "
         "- only 'Booking.com' direct inventory is used, per the brief. For 'Hotel Own Website' rows leave "
         "SoldBy as 'Booking.com' (it is ignored for that source).", False),
        ("  - Notes: anything worth flagging (sold out, minimum stay restriction, member-only price wall, etc.)", False),
        ("", False),
        ("WHAT TO FILL IN - go to the 'Hotels Reference' sheet", True),
        ("One row per hotel (fill once, not per date): StarCategory, BookingComRating (out of 10), "
         "BookingComReviewCount, OwnWebsiteURL. Use the rating shown on Booking.com at the time you collect "
         "prices - it drives the price-vs-rating value comparison in the final report.", False),
        ("", False),
        ("SHOP DATES USED FOR THIS ROUND", True),
    ]
    for d in config.SHOP_DATES:
        lines.append((f"  - {d['date']} ({d['weekday']}, {d['month']} 2026), length of stay = "
                       f"{config.LOS_NIGHTS} nights, 2 adults, 1 room", False))
    lines += [
        ("", False),
        ("RULES BAKED INTO THE ANALYSIS ENGINE (src/build_report.py)", True),
        ("  1. EXCLUDES PARTNER OFFERS: any Booking.com row with SoldBy = 'Partner / Third-Party' is dropped.", False),
        ("  2. BOOKING.COM INVENTORY ONLY: remaining Booking.com rows must be the property's own listing, "
         "not a resold/third-party rate.", False),
        ("  3. ALL PRICES CONVERTED TO EUR using the FX_TO_EUR table in src/config.py (refresh it before each "
         "round - rates move daily).", False),
        ("  4. PROMOTIONS DETECTED automatically from keywords in RatePlanOfferLabel (see PROMO_KEYWORDS in "
         "src/config.py) and highlighted in the output report.", False),
        ("  5. Rows with a blank Price are ignored (treat as 'not collected / sold out').", False),
        ("", False),
        ("HOW TO RUN", True),
        ("  1. Fill in this workbook, save it as templates/price_input_template.xlsx (keep the same file name/path, "
         "or pass a different path to build_report.py).", False),
        ("  2. From the project root: python3 src/build_report.py", False),
        ("  3. Open output/Hotel_Pricing_Competitive_Analysis.xlsx", False),
    ]
    r = 1
    for text, bold in lines:
        cell = ws.cell(row=r, column=1, value=text)
        cell.font = Font(bold=bold, size=13 if bold and r == 1 else (11.5 if bold else 11))
        cell.alignment = WRAP
        ws.row_dimensions[r].height = 30 if len(text) > 80 else 16
        r += 1
    return ws


def build_hotels_reference(wb, hotels):
    ws = wb.create_sheet("Hotels Reference")
    headers = ["HotelID", "HotelName", "District", "StarCategory (fill)",
               "BookingComRating /10 (fill)", "BookingComReviewCount (fill)",
               "OwnWebsiteURL (fill)"]
    ws.append(headers)
    fill_cols = {4, 5, 6, 7}
    yellow = PatternFill("solid", fgColor="FFF2CC")
    for h in hotels:
        ws.append([int(h["HotelID"]), h["HotelName"], h["District"], None, None, None, None])
    for row in range(2, ws.max_row + 1):
        for col in fill_cols:
            ws.cell(row=row, column=col).fill = yellow
    widths = [9, 40, 18, 20, 24, 26, 40]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    style_header(ws)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    dv = DataValidation(type="list", formula1='"Luxury 5-star,Upper Upscale 4.5-star,Upscale 4-star,'
                                              'Boutique,3-star,Apart-hotel/Other"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"D2:D{ws.max_row}")

    dv2 = DataValidation(type="decimal", operator="between", formula1=0, formula2=10, allow_blank=True,
                          error="Enter a rating between 0 and 10", showErrorMessage=True)
    ws.add_data_validation(dv2)
    dv2.add(f"E2:E{ws.max_row}")
    return ws


def build_price_entry(wb, hotels):
    ws = wb.create_sheet("Price Data Entry")
    headers = ["HotelID", "HotelName", "District", "Source", "SoldBy",
               "CheckInDate", "Nights", "RoomType (fill)", "RatePlanOfferLabel (fill)",
               "Price (fill)", "Currency (fill)", "Notes (fill)"]
    ws.append(headers)

    yellow = PatternFill("solid", fgColor="FFF2CC")
    fill_cols = {8, 9, 10, 11, 12}

    row_i = 1
    for h in hotels:
        for source in config.VALID_SOURCES:
            for d in config.SHOP_DATES:
                row_i += 1
                sold_by_default = config.SOLD_BY_DIRECT
                ws.append([
                    int(h["HotelID"]), h["HotelName"], h["District"], source, sold_by_default,
                    d["date"], config.LOS_NIGHTS, None, "Standard Rate", None, "EUR", None,
                ])
    for row in range(2, ws.max_row + 1):
        for col in fill_cols:
            ws.cell(row=row, column=col).fill = yellow

    widths = [9, 40, 18, 20, 22, 13, 8, 30, 26, 12, 11, 30]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    style_header(ws)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    last = ws.max_row
    dv_source = DataValidation(type="list", formula1=f'"{",".join(config.VALID_SOURCES)}"', allow_blank=False)
    ws.add_data_validation(dv_source)
    dv_source.add(f"D2:D{last}")

    dv_soldby = DataValidation(type="list", formula1=f'"{",".join(config.VALID_SOLD_BY)}"', allow_blank=False)
    ws.add_data_validation(dv_soldby)
    dv_soldby.add(f"E2:E{last}")

    dv_ccy = DataValidation(type="list", formula1=f'"{",".join(config.CURRENCIES)}"', allow_blank=False)
    ws.add_data_validation(dv_ccy)
    dv_ccy.add(f"K2:K{last}")

    dv_price = DataValidation(type="decimal", operator="greaterThan", formula1=0, allow_blank=True,
                               error="Price must be a positive number", showErrorMessage=True)
    ws.add_data_validation(dv_price)
    dv_price.add(f"J2:J{last}")
    return ws


def main():
    hotels = load_hotels()
    wb = Workbook()
    build_instructions(wb)
    build_hotels_reference(wb, hotels)
    build_price_entry(wb, hotels)
    config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(config.PRICE_TEMPLATE_XLSX)
    n_rows = len(hotels) * len(config.VALID_SOURCES) * len(config.SHOP_DATES)
    print(f"Wrote {config.PRICE_TEMPLATE_XLSX} - {len(hotels)} hotels x "
          f"{len(config.VALID_SOURCES)} sources x {len(config.SHOP_DATES)} dates = {n_rows} data-entry rows")


if __name__ == "__main__":
    main()
