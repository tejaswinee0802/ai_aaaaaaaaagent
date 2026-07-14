"""
Hotel Revenue Management Pricing Agent - analysis engine.

Reads the filled-in templates/price_input_template.xlsx and produces
output/Hotel_Pricing_Competitive_Analysis.xlsx:

  - Excludes Booking.com partner/third-party rows (direct inventory only)
  - Converts every price to EUR
  - Flags promotions / special offers
  - Compares Booking.com vs each hotel's own website (rate-parity check)
  - Ranks hotels against each other on price and guest rating
  - Auto-generates strategic recommendations

Usage:
    python3 src/build_report.py [input_xlsx] [output_xlsx]
"""

import sys

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.formatting.rule import CellIsRule

import config

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
PROMO_FILL = PatternFill("solid", fgColor="FFF2CC")
LEAK_FILL = PatternFill("solid", fgColor="F8CBAD")
GOOD_FILL = PatternFill("solid", fgColor="C6E0B4")
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")


# ---------------------------------------------------------------------------
# Load & clean
# ---------------------------------------------------------------------------
def _clean_col(name: str) -> str:
    name = name.split(" (fill)")[0].strip()
    name = name.split(" /10")[0].strip()
    return name


def load_data(path):
    hotels = pd.read_excel(path, sheet_name="Hotels Reference")
    hotels.columns = [_clean_col(c) for c in hotels.columns]

    prices = pd.read_excel(path, sheet_name="Price Data Entry")
    prices.columns = [_clean_col(c) for c in prices.columns]
    return hotels, prices


def is_promo(label):
    if not isinstance(label, str) or not label.strip():
        return False
    low = label.lower()
    return any(k in low for k in config.PROMO_KEYWORDS)


def clean_prices(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    n_total = len(df)

    # Drop rows with no price collected (not shopped / sold out)
    df = df[pd.to_numeric(df["Price"], errors="coerce").notna()].copy()
    df["Price"] = pd.to_numeric(df["Price"])
    n_priced = len(df)

    # CONDITION: exclude partner / third-party offers - Booking.com inventory only
    excluded_partner = df[(df["Source"] == config.SOURCE_BOOKING) &
                           (df["SoldBy"] == config.SOLD_BY_PARTNER)]
    df = df[~((df["Source"] == config.SOURCE_BOOKING) &
              (df["SoldBy"] == config.SOLD_BY_PARTNER))].copy()

    # CONDITION: price in EUR
    df["Currency"] = df["Currency"].fillna("EUR").str.upper().str.strip()
    unknown_ccy = sorted(set(df["Currency"]) - set(config.FX_TO_EUR))
    if unknown_ccy:
        raise ValueError(f"Unknown currency codes in data: {unknown_ccy}. "
                          f"Add them to FX_TO_EUR in src/config.py.")
    df["PriceEUR"] = df.apply(lambda r: round(r["Price"] * config.FX_TO_EUR[r["Currency"]], 2), axis=1)
    df["PricePerNightEUR"] = round(df["PriceEUR"] / df["Nights"].replace(0, config.LOS_NIGHTS), 2)

    df["IsPromo"] = df["RatePlanOfferLabel"].apply(is_promo)
    df["CheckInDate"] = pd.to_datetime(df["CheckInDate"]).dt.date.astype(str)

    stats = {
        "rows_in_template": n_total,
        "rows_with_price_collected": n_priced,
        "rows_excluded_partner_thirdparty": len(excluded_partner),
        "rows_in_final_analysis": len(df),
    }
    return df, stats


# ---------------------------------------------------------------------------
# Derived tables
# ---------------------------------------------------------------------------
def build_parity_table(df: pd.DataFrame, hotels: pd.DataFrame) -> pd.DataFrame:
    bcom = df[df["Source"] == config.SOURCE_BOOKING][
        ["HotelID", "HotelName", "District", "CheckInDate", "PricePerNightEUR", "RatePlanOfferLabel", "IsPromo"]
    ].rename(columns={"PricePerNightEUR": "BookingCom_EUR", "RatePlanOfferLabel": "BookingCom_Offer",
                       "IsPromo": "BookingCom_Promo"})
    own = df[df["Source"] == config.SOURCE_OWN_SITE][
        ["HotelID", "CheckInDate", "PricePerNightEUR", "RatePlanOfferLabel", "IsPromo"]
    ].rename(columns={"PricePerNightEUR": "OwnSite_EUR", "RatePlanOfferLabel": "OwnSite_Offer",
                       "IsPromo": "OwnSite_Promo"})

    merged = bcom.merge(own, on=["HotelID", "CheckInDate"], how="outer")
    merged["GapEUR"] = (merged["OwnSite_EUR"] - merged["BookingCom_EUR"]).round(2)
    merged["GapPct"] = ((merged["GapEUR"] / merged["BookingCom_EUR"]) * 100).round(1)

    def verdict(row):
        if pd.isna(row["BookingCom_EUR"]) or pd.isna(row["OwnSite_EUR"]):
            return "Incomplete data"
        if row["GapEUR"] < -0.5:
            return "Parity risk: Own site CHEAPER than Booking.com"
        if row["GapEUR"] > 0.5:
            return "Own site pricier than Booking.com"
        return "At parity"

    merged["Verdict"] = merged.apply(verdict, axis=1)
    merged = merged.sort_values(["District", "HotelName", "CheckInDate"])
    return merged


def build_ranking_table(df: pd.DataFrame, hotels: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby(["HotelID", "Source"])["PricePerNightEUR"].mean().unstack("Source")
    agg = agg.rename(columns={config.SOURCE_BOOKING: "AvgBookingCom_EUR",
                               config.SOURCE_OWN_SITE: "AvgOwnSite_EUR"})
    agg["AvgBlended_EUR"] = df.groupby("HotelID")["PricePerNightEUR"].mean()
    promo_share = df.groupby("HotelID")["IsPromo"].mean().rename("PromoSharePct") * 100
    agg = agg.join(promo_share)

    out = hotels[["HotelID", "HotelName", "District", "StarCategory", "BookingComRating"]].merge(
        agg.reset_index(), on="HotelID", how="left"
    )
    out["AvgBlended_EUR"] = out["AvgBlended_EUR"].round(2)
    out["AvgBookingCom_EUR"] = out["AvgBookingCom_EUR"].round(2)
    out["AvgOwnSite_EUR"] = out["AvgOwnSite_EUR"].round(2)
    out["PromoSharePct"] = out["PromoSharePct"].round(0)

    rated = out[out["BookingComRating"].notna() & out["AvgBlended_EUR"].notna() & (out["AvgBlended_EUR"] > 0)].copy()
    rated["ValueScore"] = (rated["BookingComRating"] / rated["AvgBlended_EUR"] * 100).round(3)
    out = out.merge(rated[["HotelID", "ValueScore"]], on="HotelID", how="left")

    out["OverallPriceRank"] = out["AvgBlended_EUR"].rank(method="min", ascending=True)
    out["DistrictPriceRank"] = out.groupby("District")["AvgBlended_EUR"].rank(method="min", ascending=True)
    out["ValueRank"] = out["ValueScore"].rank(method="min", ascending=False)

    out = out.sort_values("AvgBlended_EUR", na_position="last")
    return out


def build_promo_log(df: pd.DataFrame) -> pd.DataFrame:
    promos = df[df["IsPromo"]][
        ["HotelID", "HotelName", "District", "Source", "CheckInDate",
         "RatePlanOfferLabel", "PricePerNightEUR", "Notes"]
    ].sort_values(["District", "HotelName", "Source", "CheckInDate"])
    return promos


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
def build_recommendations(df, parity, ranking, promos, stats, hotels):
    lines = []
    n_hotels_priced = ranking["AvgBlended_EUR"].notna().sum()
    lines.append(("DATA COVERAGE", True))
    lines.append((f"{stats['rows_in_final_analysis']} priced rate observations analyzed across "
                   f"{n_hotels_priced} of {len(hotels)} hotels, {len(config.SHOP_DATES)} shop dates "
                   f"({', '.join(d['date'] for d in config.SHOP_DATES)}), after excluding "
                   f"{stats['rows_excluded_partner_thirdparty']} Booking.com partner/third-party rows and "
                   f"{stats['rows_with_price_collected'] - stats['rows_in_final_analysis'] + stats['rows_excluded_partner_thirdparty']} "
                   f"rows with no price collected.", False))
    if n_hotels_priced < len(hotels):
        lines.append((f"NOTE: {len(hotels) - n_hotels_priced} hotels have no priced data yet in this round - "
                       f"fill in the remaining rows in 'Price Data Entry' for full 110-hotel coverage.", False))
    lines.append(("", False))

    # Rate parity leaks
    leaks = parity[parity["Verdict"].str.startswith("Parity risk", na=False)]
    lines.append(("RATE PARITY", True))
    if len(leaks):
        worst = leaks.sort_values("GapPct").head(5)
        names = ", ".join(f"{r.HotelName} ({r.CheckInDate}: {r.GapPct}%)" for r in worst.itertuples())
        lines.append((f"{len(leaks)} observation(s) show the hotel's OWN WEBSITE priced cheaper than its "
                       f"Booking.com listing - a rate-parity leak that lets guests undercut the OTA on the "
                       f"brand's own channel (or signals Booking.com is not matching a direct promotion). "
                       f"Worst gaps: {names}. Recommendation: align direct-site promotions with OTA rate "
                       f"parity clauses, or intentionally use a controlled direct-only perk (free breakfast, "
                       f"late checkout) instead of a lower headline price to stay compliant while still "
                       f"incentivising direct bookings.", False))
    else:
        lines.append(("No rate-parity leaks detected in this round's sample - Booking.com direct-inventory "
                       "prices were at or below own-website prices in all matched observations.", False))
    lines.append(("", False))

    # Promotion dependency
    lines.append(("PROMOTIONAL PRESSURE", True))
    if len(promos):
        by_hotel = promos.groupby("HotelName").size().sort_values(ascending=False)
        heavy = by_hotel[by_hotel >= 3]
        lines.append((f"{len(promos)} of {stats['rows_in_final_analysis']} priced observations "
                       f"({round(100*len(promos)/max(stats['rows_in_final_analysis'],1))}%) carried a "
                       f"promotion or special-offer label (Genius, mobile rate, early bird, member pricing, "
                       f"etc.).", False))
        if len(heavy):
            names = ", ".join(f"{n} ({c} of {len(config.SHOP_DATES)*2} shops)" for n, c in heavy.items())
            lines.append((f"Hotels discounting on most shops checked: {names}. Recommendation: review whether "
                           f"these are structural (channel-manager default discounts) rather than tactical - "
                           f"heavy, near-permanent discounting compresses ADR and trains guests to wait for "
                           f"deals.", False))
    else:
        lines.append(("No promotional/discounted rates detected in this round's sample.", False))
    lines.append(("", False))

    # Price vs rating positioning
    lines.append(("PRICE vs RATING POSITIONING", True))
    valued = ranking[ranking["ValueScore"].notna()]
    if len(valued) >= 2:
        avg_price = valued["AvgBlended_EUR"].mean()
        avg_rating = valued["BookingComRating"].mean()
        overpriced = valued[(valued["AvgBlended_EUR"] > avg_price) & (valued["BookingComRating"] < avg_rating)]
        underpriced = valued[(valued["AvgBlended_EUR"] < avg_price) & (valued["BookingComRating"] > avg_rating)]
        best_value = valued.sort_values("ValueScore", ascending=False).head(5)
        if len(overpriced):
            names = ", ".join(overpriced.sort_values("AvgBlended_EUR", ascending=False)["HotelName"].head(5))
            lines.append((f"Priced ABOVE the competitive-set average (EUR {avg_price:.0f}/night) while rated "
                           f"BELOW the average guest rating ({avg_rating:.1f}/10): {names}. Recommendation: "
                           f"these properties are exposed on OTAs to guests comparing price-to-rating side by "
                           f"side - either justify the premium with visible product upgrades/marketing, or "
                           f"trim rate to defend occupancy.", False))
        if len(underpriced):
            names = ", ".join(underpriced.sort_values("AvgBlended_EUR")["HotelName"].head(5))
            lines.append((f"Priced BELOW the competitive-set average while rated ABOVE the average rating: "
                           f"{names}. Recommendation: these have room to test rate increases or reduce promo "
                           f"dependency - guest satisfaction is already outperforming the price point.", False))
        names = ", ".join(f"{r.HotelName} ({r.ValueScore:.2f})" for r in best_value.itertuples())
        lines.append((f"Best price-to-rating value scores this round (higher = more rating per EUR): {names}. "
                       f"These set the practical 'value' bar the rest of the set is being compared against.", False))
    else:
        lines.append(("Not enough hotels with both a rating and a price collected yet to compute "
                       "price-vs-rating positioning - fill in more of the template.", False))
    lines.append(("", False))

    # District view
    lines.append(("DISTRICT-LEVEL POSITIONING", True))
    dist = ranking[ranking["AvgBlended_EUR"].notna()].groupby("District")["AvgBlended_EUR"].agg(["mean", "count"])
    if len(dist):
        dist = dist.sort_values("mean", ascending=False)
        summary = "; ".join(f"{d}: avg EUR {row['mean']:.0f}/night (n={int(row['count'])})"
                             for d, row in dist.iterrows())
        lines.append((summary, False))
        lines.append(("Recommendation: benchmark new-build or repositioning rate strategy against the district "
                       "average first, then against named direct competitors within that district - cross-"
                       "district comparisons mix very different product tiers (e.g. Grand Baie/Flacq 5-star "
                       "resorts vs Port Louis city hotels).", False))
    lines.append(("", False))

    lines.append(("NEXT STEPS", True))
    lines.append(("  1. Repeat this shop on a recurring cadence (e.g. weekly) to track how competitor pricing "
                   "moves as the August/September/October dates approach - single-snapshot pricing can be "
                   "misleading if a competitor is mid-flash-sale.", False))
    lines.append(("  2. Extend the FX_TO_EUR table refresh into the weekly routine - a stale FX snapshot will "
                   "silently skew the EUR comparison.", False))
    lines.append(("  3. Where a parity leak or heavy promo dependency was flagged, verify manually before "
                   "acting - screenshot the live rate, since OTA displays are dynamic and can change within "
                   "the same day.", False))
    return lines


# ---------------------------------------------------------------------------
# Excel writing helpers
# ---------------------------------------------------------------------------
def write_df_sheet(wb, name, df, promo_col=None, highlight_rules=None, col_widths=None):
    ws = wb.create_sheet(name)
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions

    cols = list(df.columns)
    if promo_col and promo_col in cols:
        pidx = cols.index(promo_col) + 1
        for row in range(2, ws.max_row + 1):
            if ws.cell(row=row, column=pidx).value is True:
                for c in range(1, len(cols) + 1):
                    ws.cell(row=row, column=c).fill = PROMO_FILL

    if highlight_rules:
        for col_name, matcher, fill in highlight_rules:
            if col_name not in cols:
                continue
            cidx = cols.index(col_name) + 1
            for row in range(2, ws.max_row + 1):
                val = ws.cell(row=row, column=cidx).value
                if matcher(val):
                    for c in range(1, len(cols) + 1):
                        ws.cell(row=row, column=c).fill = fill

    widths = col_widths or [18] * len(cols)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    return ws


def write_summary_sheet(wb, stats, hotels, ranking):
    ws = wb.create_sheet("Executive Summary", 0)
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 58
    title = ws.cell(row=1, column=1, value="Hotel Revenue Management - Competitive Pricing Analysis")
    title.font = Font(bold=True, size=15)
    ws.cell(row=2, column=1, value="Mauritius competitive set - Booking.com vs Hotel Own Website")
    ws.cell(row=2, column=1).font = Font(italic=True, size=11)

    r = 4
    rows = [
        ("Shop dates", ", ".join(f"{d['date']} ({d['weekday']}, {d['month']} 2026)" for d in config.SHOP_DATES)),
        ("Length of stay", f"{config.LOS_NIGHTS} nights"),
        ("Hotels in competitive set", len(hotels)),
        ("Hotels with priced data this round", int(ranking["AvgBlended_EUR"].notna().sum())),
        ("Rows collected (priced)", stats["rows_with_price_collected"]),
        ("Rows excluded - partner/third-party (Booking.com)", stats["rows_excluded_partner_thirdparty"]),
        ("Rows in final EUR-normalised analysis", stats["rows_in_final_analysis"]),
        ("FX snapshot date (src/config.py)", config.FX_SNAPSHOT_DATE),
        ("Currency", "EUR (all prices converted)"),
        ("Filtering rules applied", "Booking.com direct inventory only (partner/third-party excluded); "
                                     "price per night; EUR-normalised"),
    ]
    for label, val in rows:
        ws.cell(row=r, column=1, value=label).font = BOLD
        ws.cell(row=r, column=2, value=val)
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Sheets in this workbook").font = Font(bold=True, size=12)
    r += 1
    sheet_desc = [
        ("Booking.com Pricing", "EUR price per hotel/date, Booking.com direct inventory only, promos highlighted"),
        ("Own Website Pricing", "EUR price per hotel/date from each hotel's own site, promos highlighted"),
        ("Rate Parity Comparison", "Booking.com vs Own Website side by side, parity leaks highlighted"),
        ("Cross-Hotel Ranking & Rating", "Avg EUR price, Booking.com guest rating, value score, rank vs all hotels and within district"),
        ("Promotions Log", "Every rate observation flagged as a promotion / special offer"),
        ("Strategic Recommendations", "Auto-generated insights and recommended actions from the data above"),
    ]
    for name, desc in sheet_desc:
        ws.cell(row=r, column=1, value=name).font = BOLD
        ws.cell(row=r, column=2, value=desc).alignment = WRAP
        r += 1
    return ws


def write_recommendations_sheet(wb, lines):
    ws = wb.create_sheet("Strategic Recommendations")
    ws.column_dimensions["A"].width = 130
    r = 1
    ws.cell(row=r, column=1, value="Strategic Recommendations").font = Font(bold=True, size=15)
    r += 2
    for text, bold in lines:
        cell = ws.cell(row=r, column=1, value=text)
        cell.font = Font(bold=bold, size=12 if bold else 11)
        cell.alignment = WRAP
        ws.row_dimensions[r].height = max(16, 15 * (1 + len(text) // 150))
        r += 1
    return ws


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else str(config.PRICE_TEMPLATE_XLSX)
    out_path = sys.argv[2] if len(sys.argv) > 2 else str(config.OUTPUT_DIR / "Hotel_Pricing_Competitive_Analysis.xlsx")

    hotels, raw_prices = load_data(in_path)
    df, stats = clean_prices(raw_prices)

    parity = build_parity_table(df, hotels)
    ranking = build_ranking_table(df, hotels)
    promos = build_promo_log(df)
    reco_lines = build_recommendations(df, parity, ranking, promos, stats, hotels)

    wb = Workbook()
    wb.remove(wb.active)

    write_summary_sheet(wb, stats, hotels, ranking)

    bcom_cols = ["HotelID", "HotelName", "District", "CheckInDate", "RoomType",
                 "RatePlanOfferLabel", "Price", "Currency", "PriceEUR", "PricePerNightEUR", "IsPromo", "Notes"]
    bcom = df[df["Source"] == config.SOURCE_BOOKING][bcom_cols].sort_values(["District", "HotelName", "CheckInDate"])
    write_df_sheet(wb, "Booking.com Pricing", bcom, promo_col="IsPromo",
                   col_widths=[9, 38, 16, 12, 26, 24, 10, 10, 11, 15, 9, 26])

    own = df[df["Source"] == config.SOURCE_OWN_SITE][bcom_cols].sort_values(["District", "HotelName", "CheckInDate"])
    write_df_sheet(wb, "Own Website Pricing", own, promo_col="IsPromo",
                   col_widths=[9, 38, 16, 12, 26, 24, 10, 10, 11, 15, 9, 26])

    write_df_sheet(
        wb, "Rate Parity Comparison", parity,
        highlight_rules=[("Verdict", lambda v: isinstance(v, str) and v.startswith("Parity risk"), LEAK_FILL),
                          ("Verdict", lambda v: v == "At parity", GOOD_FILL)],
        col_widths=[9, 38, 16, 12, 15, 24, 13, 14, 24, 13, 12, 30],
    )

    write_df_sheet(wb, "Cross-Hotel Ranking & Rating", ranking,
                   col_widths=[9, 38, 16, 16, 14, 16, 15, 15, 14, 13, 15, 16, 11])

    write_df_sheet(wb, "Promotions Log", promos,
                   col_widths=[9, 38, 16, 20, 13, 26, 15, 30])

    write_recommendations_sheet(wb, reco_lines)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(out_path)
    print(f"Wrote {out_path}")
    print(stats)


if __name__ == "__main__":
    main()
