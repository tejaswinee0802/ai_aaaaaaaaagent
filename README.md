# Hotel Revenue Management Pricing Agent

A competitive-pricing analysis tool for a 110-hotel Mauritius set (Black
River, Flacq, Grand Port, Grand Baie, Moka, Pamplemousses, Plaine Wilhems,
Port Louis, Rivière du Rempart, Savanne), comparing **Booking.com** vs each
hotel's **own website**.

## What it does

1. Generates an Excel data-collection template covering all 110 hotels x
   2 sources (Booking.com, Own Website) x 3 shop dates - one random date per
   month for August, September and October.
2. You (or staff) manually fill in the observed prices, currency, rate-plan
   label, and whether the Booking.com rate is the property's own inventory
   or a partner/third-party rate.
3. The analysis engine:
   - **Excludes partner/third-party offers** - only Booking.com's own
     (direct) inventory is analyzed, per the brief.
   - **Converts every price to EUR** using an editable FX table.
   - **Detects promotions/special offers** from the rate-plan label
     (Genius, mobile rate, early bird, member pricing, etc.) and highlights
     them in the report.
   - **Compares Booking.com vs the hotel's own website** per hotel per
     date, flagging rate-parity leaks (own site cheaper than Booking.com).
   - **Ranks hotels against each other** on price and Booking.com guest
     rating (a price-per-rating "value score"), overall and within
     district.
   - **Auto-generates strategic recommendations** from the numbers above.

### Why manual data entry, not a live scraper

Booking.com's terms of service prohibit automated/bot scraping, and its
pages are JS-rendered so a simple HTTP fetch won't return real prices.
Rather than build something that fights Booking.com's anti-bot defenses
(fragile, ToS risk, and impossible to run unattended across 110
properties), this tool separates **data collection** (manual, one page at
a time, exactly like a human revenue manager would shop the competition)
from **analysis** (fully automated, reusable every time you re-shop).

## Project layout

```
data/hotels_master.csv          Master list of all 110 hotels + district
src/config.py                   Shop dates, FX rates, promo keywords, filter rules
src/generate_template.py        Builds templates/price_input_template.xlsx
src/build_report.py             Reads a filled template -> builds the final report
src/demo_fill_sample.py         Fills a labeled SAMPLE subset for testing the pipeline
templates/                      Generated input template(s) live here
output/                         Generated report(s) land here
```

## Usage

```bash
pip install -r requirements.txt

# 1. Generate the blank data-collection template (660 rows: 110 hotels x
#    2 sources x 3 dates). Re-run any time to regenerate from a clean slate.
python3 src/generate_template.py
# -> templates/price_input_template.xlsx

# 2. Open templates/price_input_template.xlsx and fill in the yellow cells:
#    - "Hotels Reference" sheet: Star category, Booking.com rating (once per hotel)
#    - "Price Data Entry" sheet: room type, rate-plan/offer label, price,
#      currency, and (Booking.com rows only) whether it's Booking.com's own
#      inventory or a partner/third-party rate
#    Full instructions are in the "Instructions" sheet of the workbook.

# 3. Build the analysis report from your filled-in template.
python3 src/build_report.py
# -> output/Hotel_Pricing_Competitive_Analysis.xlsx
```

You can also point both scripts at custom paths:

```bash
python3 src/build_report.py path/to/your_filled_template.xlsx path/to/report.xlsx
```

## Report contents (output workbook)

| Sheet | Contents |
|---|---|
| Executive Summary | Shop dates, data coverage, filtering rules applied |
| Booking.com Pricing | EUR price per hotel/date, direct-inventory only, promos highlighted |
| Own Website Pricing | EUR price per hotel/date from the hotel's own site, promos highlighted |
| Rate Parity Comparison | Booking.com vs Own Website side by side, gap %, parity leaks highlighted |
| Cross-Hotel Ranking & Rating | Avg EUR price, guest rating, value score, rank vs all hotels and within district |
| Promotions Log | Every observation flagged as a promotion / special offer |
| Strategic Recommendations | Auto-generated insights: parity leaks, promo dependency, price-vs-rating positioning, district benchmarks, next steps |

## Demo / sample data

`src/demo_fill_sample.py` fills a 12-hotel subset with clearly-labeled
**illustrative, non-real** prices so you can see the full pipeline run
end-to-end before collecting real data:

```bash
python3 src/demo_fill_sample.py
python3 src/build_report.py templates/DEMO_SAMPLE_price_input_template.xlsx output/Hotel_Pricing_Competitive_Analysis_DEMO.xlsx
```

Every demo row is tagged `SAMPLE/DEMO DATA - not a real observed rate` in
its Notes column - do not use the demo output for real pricing decisions.

## Keeping it current

- **FX rates drift daily.** Refresh `FX_TO_EUR` in `src/config.py` before
  each real data-collection round.
- **Shop dates are fixed per round.** Call `config.pick_random_dates()` to
  draw a fresh random date per month, then regenerate the template.
- **Re-shop regularly** (e.g. weekly) - a single snapshot can be skewed if
  a competitor happens to be mid-flash-sale on the day you check.
