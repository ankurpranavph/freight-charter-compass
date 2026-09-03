"""
Download and parse the World Bank Commodity Markets ("Pink Sheet") monthly
historical data file, extract Coal (Australian) and Crude oil (Brent), and
write a long-format CSV to data_pipeline/processed/.

REAL DATA: World Bank Commodity Markets. Free, official, monthly since 1960.
https://www.worldbank.org/en/research/commodity-markets

*** Known limitation of this dev setup — read before assuming this is broken ***
Both of Claude's execution environments for this project (the cloud sandbox
and the local device-bridge shell) sit behind an organisation network policy
that blocks direct requests to thedocs.worldbank.org (confirmed: raw curl to
this exact URL returns a connection failure from both). So this script is
written correctly but has NOT been execution-tested against the live file —
only against a synthetic file matching the documented Pink Sheet layout (see
tests/test_ingest_worldbank.py). It needs to be run from a normal terminal
with unrestricted internet — i.e. yours. If the real file's layout differs
from what's assumed below (see PARSING NOTES), it will fail with a clear
error rather than silently importing garbage — tell Claude what it prints
and we'll fix the real mismatch together.

PARSING NOTES (Pink Sheet "Monthly Prices" sheet, as documented/observed
historically — verify against the real file):
- Wide format: commodities down column A, one column per month.
- Month columns are labelled like "1960M01", "1960M02", ... "2026M08".
- We find the header row dynamically (the row with the most cells matching
  that pattern) rather than assuming a fixed row number, so a shifted title
  block doesn't silently break the script.
- Commodity row match is a case-insensitive substring, not an exact string,
  since exact wording has varied release to release (e.g. "Coal, Australian"
  vs "Coal, Australian thermal coal").
"""
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parent / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent / "processed"

SOURCE_URL = (
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-"
    "0050012026/related/CMO-Historical-Data-Monthly.xlsx"
)

# (output commodity key, substring to match in column A, output unit)
TARGET_COMMODITIES = [
    ("coal_australian", "coal, australian", "usd_per_tonne"),
    ("crude_oil_brent", "crude oil, brent", "usd_per_bbl"),
]

MONTH_COL_RE = re.compile(r"^\d{4}M\d{2}$")


def download(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(SOURCE_URL, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def find_header_row(raw: pd.DataFrame) -> int:
    """The row with the most cells matching '1960M01'-style month labels."""
    best_row, best_count = None, 0
    for i in range(min(20, len(raw))):
        count = sum(
            bool(MONTH_COL_RE.match(str(v).strip()))
            for v in raw.iloc[i].tolist()
        )
        if count > best_count:
            best_row, best_count = i, count
    if best_row is None or best_count < 1:
        raise ValueError(
            "Could not find a Pink Sheet header row with month labels like "
            "'1960M01'. The file's layout may have changed — open it in "
            "Excel and check the 'Monthly Prices' sheet."
        )
    return best_row


def month_label_to_date(label: str) -> str:
    year, month = label.split("M")
    return date(int(year), int(month), 1).isoformat()


def parse(xlsx_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name="Monthly Prices", header=None)
    header_row = find_header_row(raw)

    header = raw.iloc[header_row]
    month_cols = [
        c for c in raw.columns
        if MONTH_COL_RE.match(str(header[c]).strip())
    ]
    if not month_cols:
        raise ValueError("Found a header row but no month columns matched.")

    commodity_col = raw.columns[0]
    data_rows = raw.iloc[header_row + 1:]

    records = []
    for key, needle, unit in TARGET_COMMODITIES:
        matches = data_rows[
            data_rows[commodity_col].astype(str).str.lower().str.contains(needle, na=False)
        ]
        if matches.empty:
            print(f"WARNING: no row matched '{needle}' — skipping {key}", file=sys.stderr)
            continue
        row = matches.iloc[0]
        for c in month_cols:
            price = row[c]
            if pd.isna(price):
                continue
            records.append({
                "date": month_label_to_date(str(header[c]).strip()),
                "commodity": key,
                "price_usd": float(price),
                "unit": unit,
                "source": "World Bank Commodity Markets (Pink Sheet), Monthly Prices",
                "source_url": SOURCE_URL,
            })

    if not records:
        raise ValueError(
            "Parsed the file but matched zero rows for our target commodities. "
            "The commodity name text has likely changed — check TARGET_COMMODITIES."
        )
    return pd.DataFrame.from_records(records)


def main():
    raw_path = RAW_DIR / f"worldbank_pink_sheet_{date.today().isoformat()}.xlsx"
    print(f"Downloading {SOURCE_URL} ...")
    download(raw_path)
    print(f"Saved raw file to {raw_path}")

    df = parse(raw_path)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "commodity_prices_worldbank.csv"
    df.sort_values(["commodity", "date"]).to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df.groupby("commodity")["date"].agg(["min", "max", "count"]))


if __name__ == "__main__":
    main()
