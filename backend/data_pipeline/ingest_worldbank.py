"""
Download and parse the World Bank Commodity Markets ("Pink Sheet") monthly
historical data file, extract Coal (Australian) and Crude oil (Brent), and
write a long-format CSV to data_pipeline/processed/.

REAL DATA: World Bank Commodity Markets. Free, official, monthly since 1960.
https://www.worldbank.org/en/research/commodity-markets

PARSING NOTES (Pink Sheet "Monthly Prices" sheet - confirmed against the
real CMO-Historical-Data-Monthly.xlsx file on 2026-09-03, not guessed):
- Rows 0-3: title/metadata text in column A only.
- One header row has commodity names across the columns (column A is blank
  on this row) - e.g. col 1 "Crude oil, average", col 2 "Crude oil, Brent",
  col 5 "Coal, Australian".
- The row directly below that has units in parentheses, e.g. "($/bbl)",
  "($/mt)".
- From there down, column A holds month labels like "1960M01", and each
  other column holds that commodity's price for that month.
- Missing months are marked with the literal string '...' (ellipsis), not a
  blank cell or NaN - must be handled explicitly.
- This is the OPPOSITE orientation from the previous version of this
  script, which (going by older Pink Sheet documentation) assumed
  commodities down column A and months across the columns. World Bank
  appears to have changed the file's layout since that documentation was
  written. Rather than hardcode row/column numbers, we detect the date
  column, the first data row, and the header row dynamically, so a future
  layout shift fails loudly (clear ValueError) instead of silently
  importing garbage.
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

# (output commodity key, substring to match in the header row, output unit)
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


def find_date_column(raw: pd.DataFrame) -> int:
    """The column with the most cells matching '1960M01'-style month labels
    when scanned down - this file has months running down rows, in a single
    left-hand date column (normally column 0)."""
    best_col, best_count = None, 0
    scan_rows = min(60, len(raw))
    for j in range(raw.shape[1]):
        count = sum(
            bool(MONTH_COL_RE.match(str(v).strip()))
            for v in raw.iloc[:scan_rows, j]
        )
        if count > best_count:
            best_col, best_count = j, count
    if best_col is None or best_count < 1:
        raise ValueError(
            "Could not find a date column with month labels like '1960M01' "
            "anywhere in the sheet. The file's layout may have changed - "
            "open it in Excel and check the 'Monthly Prices' sheet."
        )
    return best_col


def find_first_data_row(raw: pd.DataFrame, date_col: int) -> int:
    for i in range(len(raw)):
        if MONTH_COL_RE.match(str(raw.iat[i, date_col]).strip()):
            return i
    raise ValueError("Found a date column but no row in it matches a month label.")


def find_header_row(raw: pd.DataFrame, date_col: int, first_data_row: int) -> int:
    """Search upward from the first data row for the nearest row where most
    non-date-column cells are commodity-name text - skipping a units row
    (cells like '($/bbl)') if there is one in between."""
    non_date_col_count = raw.shape[1] - 1
    threshold = max(3, non_date_col_count // 4)
    for i in range(first_data_row - 1, max(first_data_row - 8, -1), -1):
        text_cells = 0
        for j in range(raw.shape[1]):
            if j == date_col:
                continue
            v = raw.iat[i, j]
            if isinstance(v, str) and v.strip() and not v.strip().startswith("("):
                text_cells += 1
        if text_cells >= threshold:
            return i
    raise ValueError(
        "Could not find a commodity-name header row above the first data "
        "row. The file's layout may have changed - open it in Excel and "
        "check the 'Monthly Prices' sheet."
    )


def month_label_to_date(label: str) -> str:
    year, month = label.split("M")
    return date(int(year), int(month), 1).isoformat()


def _to_price(value):
    """World Bank marks a missing month with '...' (ellipsis), not a blank
    cell - treat anything that isn't a real number as missing."""
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse(xlsx_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name="Monthly Prices", header=None)

    date_col = find_date_column(raw)
    first_data_row = find_first_data_row(raw, date_col)
    header_row = find_header_row(raw, date_col, first_data_row)
    header = raw.iloc[header_row]

    records = []
    for key, needle, unit in TARGET_COMMODITIES:
        matching_cols = [
            j for j in range(raw.shape[1])
            if j != date_col and needle in str(header[j]).strip().lower()
        ]
        if not matching_cols:
            print(f"WARNING: no column matched '{needle}' - skipping {key}", file=sys.stderr)
            continue
        col = matching_cols[0]

        for i in range(first_data_row, len(raw)):
            label = str(raw.iat[i, date_col]).strip()
            if not MONTH_COL_RE.match(label):
                continue
            price = _to_price(raw.iat[i, col])
            if price is None:
                continue
            records.append({
                "date": month_label_to_date(label),
                "commodity": key,
                "price_usd": price,
                "unit": unit,
                "source": "World Bank Commodity Markets (Pink Sheet), Monthly Prices",
                "source_url": SOURCE_URL,
            })

    if not records:
        raise ValueError(
            "Parsed the file but matched zero rows for our target commodities. "
            "The commodity name text has likely changed - check TARGET_COMMODITIES."
        )
    return pd.DataFrame.from_records(records)


def main():
    raw_path = RAW_DIR / f"worldbank_pink_sheet_{date.today().isoformat()}.xlsx"
    if raw_path.exists():
        print(f"Reusing already-downloaded {raw_path}")
    else:
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
