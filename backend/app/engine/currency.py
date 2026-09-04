"""
Module 8: INR secondary currency display.

Deliberately deferred at the Hour 23-27 checkpoint when the user first
asked about USD vs. INR for an SIH (Ministry of Steel) submission (see
DECISIONS.md #20) — built now that the 3-page MVP and both named
problem-statement gaps are closed and the user picked this as the next
item.

USD stays the sole primary/source-of-truth currency throughout the rest
of the engine and API — every REAL price this app uses (World Bank Pink
Sheet commodity prices, Ship & Bunker VLSFO bunker price, HandyBulk
time-charter day rates, IndexBox's coking-coal snapshot) is genuinely
USD-denominated in the real world; that's how international dry-bulk
freight and commodity trade are actually priced. INR is added ONLY as a
secondary, clearly-labelled CALCULATED conversion of an already-real USD
figure, using the one cited, dated exchange rate below — never a silent
wholesale switch of the underlying numbers, which would inject an
unsourced, undated FX assumption into figures that are currently clean
REAL data. Every place this app shows INR, it shows the USD figure right
alongside it, never INR alone.

RATE, single point-in-time market reference, not a live feed — same
treatment as voyage.py's bunker price and time-charter rates: a constant
with a source and a date, refreshed on a schedule in a production
system, not here. Cross-checked against a second source before being
set: Trading Economics' USD/INR spot quote (94.4290-94.4380 intraday) on
2026-09-04 agrees within ~0.5% of State Bank of India's same-day forex
card rate (TT Buy 94.13 / TT Sell 94.98) — two independent sources
converging on the same figure, not a single unverified number.
"""

USD_TO_INR_RATE = 94.43
USD_TO_INR_SOURCE = "Trading Economics, USD/INR spot rate, 2026-09-04"
USD_TO_INR_SOURCE_URL = "https://tradingeconomics.com/india/currency"
USD_TO_INR_SOURCE_DATE = "2026-09-04"


def usd_to_inr(usd: float) -> float:
    """CALCULATED, not REAL — a pure conversion of an already-real USD
    figure, see module docstring."""
    return usd * USD_TO_INR_RATE


def as_dict() -> dict:
    return {
        "usd_to_inr_rate": USD_TO_INR_RATE,
        "source": USD_TO_INR_SOURCE,
        "source_url": USD_TO_INR_SOURCE_URL,
        "source_date": USD_TO_INR_SOURCE_DATE,
    }
