"""
Download and parse the Reserve Bank of Australia's Index of Commodity
Prices historical spreadsheet, extract the Coking coal series, and write a
long-format CSV to data_pipeline/processed/ in the same shape
ingest_worldbank.py already produces.

WHY THIS EXISTS: the World Bank Pink Sheet (ingest_worldbank.py) has no
coking (metallurgical) coal series at all -- only thermal coal ("Coal,
Australia"/"Coal, Colombia"/"Coal, South Africa"), confirmed by fetching
the real Pink Sheet's column headers. SAIL procures coking coal for
steelmaking, not thermal coal, so "coal_australian" alone was a real,
documented proxy gap against the SIH26006 problem statement (see
DECISIONS.md #23). The RBA's Index of Commodity Prices explicitly tracks
"Coking coal" as its own component, separate from "Thermal coal" --
confirmed by fetching RBA's own monthly release commentary, which names
both -- and it is Australian-origin, matching this app's own
NEWCASTLE_AU origin port.

REAL DATA: Reserve Bank of Australia, Index of Commodity Prices. Free,
official, published monthly. https://www.rba.gov.au/statistics/frequency/commodity-prices/

IMPORTANT -- UNVERIFIED LAYOUT, UNLIKE ingest_worldbank.py: Claude's
execution environments (cloud sandbox and this project's device-bridge
shell) cannot reach rba.gov.au directly -- confirmed by a direct
connection test, same organisation-level egress policy documented in
DECISIONS.md #10. Unlike the World Bank parser (whose layout was
confirmed against the real downloaded file), this parser's assumed
layout is built from RBA's well-documented, standard statistical-table
convention (a metadata block with one label per row in column A --
Description / Frequency / Type / Unit / Source / Publication date /
Series ID -- then dated data rows below), NOT a confirmed dump of the
real i02hist.xlsx file. It has NOT been run against the real file by
Claude. Every lookup below is done by SEARCHING for a label or a
date-shaped column rather than a hardcoded row/column number, precisely
so that if the real file's layout differs in the details, this still has
a real chance of finding the right data -- but a first real run by the
user may reveal a genuine layout surprise and need a follow-up parser
fix, exactly as happened with the World Bank file (see DECISIONS.md #12).
Report back what the real run shows; don't assume this is correct until
it's been run for real.
"""
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parent / "raw"
PROCESSED_DIR = Path(__file__).resolve().parent / "processed"

SOURCE_URL = "https://www.rba.gov.au/statistics/tables/xls/i02hist.xlsx"

TARGET_COMMODITY_KEY = "coking_coal"
TARGET_LABEL_NEEDLE = "coking coal"  # matched case-insensitively, substring

DESCRIPTION_ROW_LABEL = "description"

DATE_LIKE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")  # e.g. "1985-01" or "1985-01-01"


def download(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(SOURCE_URL, timeout=60)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest


def find_row_by_label(raw: pd.DataFrame, label: str) -> int:
    """Scan column A (and, defensively, the first few columns, in case the
    label isn't strictly in column A) for a cell whose stripped text
    case-insensitively equals `label`."""
    label = label.strip().lower()
    scan_cols = min(3, raw.shape[1])
    for i in range(len(raw)):
        for j in range(scan_cols):
            v = raw.iat[i, j]
            if isinstance(v, str) and v.strip().lower() == label:
                return i
    raise ValueError(
        f"Could not find a row labelled '{label}' in the first {scan_cols} "
        "columns. The file's layout may differ from what this parser "
        "assumes -- open it and check where series metadata (Description/"
        "Unit/Series ID rows) actually lives, then update this parser. "
        "See the module docstring."
    )


def find_target_column(raw: pd.DataFrame, description_row: int) -> int:
    """Search the description row for a cell containing our target
    commodity's name, case-insensitive substring match."""
    needle = TARGET_LABEL_NEEDLE.lower()
    for j in range(raw.shape[1]):
        v = raw.iat[description_row, j]
        if isinstance(v, str) and needle in v.strip().lower():
            return j
    raise ValueError(
        f"Found a Description row (row {description_row}) but no column "
        f"in it mentions '{TARGET_LABEL_NEEDLE}'. RBA may have renamed or "
        "restructured this series -- open the file and check the "
        "Description row's exact text, then update TARGET_LABEL_NEEDLE."
    )


def _cell_to_iso_date(value) -> str | None:
    """Accepts a real Excel date (pandas/openpyxl hands these back as
    datetime/Timestamp), or a date-shaped string. Returns an ISO date
    string (first-of-month) or None if this cell isn't a date at all."""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return date(value.year, value.month, 1).isoformat()
    if isinstance(value, str):
        s = value.strip()
        if DATE_LIKE_RE.match(s):
            parts = s.split("-")
            return date(int(parts[0]), int(parts[1]), 1).isoformat()
    return None


def find_date_column(raw: pd.DataFrame, after_row: int) -> int:
    """The column with the most date-shaped cells below `after_row` --
    this file is assumed to have one left-hand date column, same
    convention as the World Bank file."""
    best_col, best_count = None, 0
    scan_rows = min(80, len(raw) - after_row - 1)
    for j in range(raw.shape[1]):
        count = sum(
            _cell_to_iso_date(raw.iat[after_row + 1 + i, j]) is not None
            for i in range(scan_rows)
        )
        if count > best_count:
            best_col, best_count = j, count
    if best_col is None or best_count < 1:
        raise ValueError(
            "Could not find a date column below the metadata block. The "
            "file's layout may differ from what this parser assumes."
        )
    return best_col


def find_first_data_row(raw: pd.DataFrame, date_col: int, after_row: int) -> int:
    for i in range(after_row + 1, len(raw)):
        if _cell_to_iso_date(raw.iat[i, date_col]) is not None:
            return i
    raise ValueError("Found a date column but no dated row below the metadata block.")


def find_unit_label(raw: pd.DataFrame, target_col: int) -> str:
    """Best-effort: if a row labelled 'Unit' exists, read this column's
    value from it. Never fabricated -- 'unknown' if not found, so a wrong
    guess never silently becomes a false unit label downstream."""
    try:
        unit_row = find_row_by_label(raw, "unit")
    except ValueError:
        return "unknown"
    v = raw.iat[unit_row, target_col]
    return str(v).strip() if isinstance(v, str) and v.strip() else "unknown"


def parse(xlsx_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(xlsx_path, sheet_name=0, header=None)

    description_row = find_row_by_label(raw, DESCRIPTION_ROW_LABEL)
    target_col = find_target_column(raw, description_row)
    unit = find_unit_label(raw, target_col)
    date_col = find_date_column(raw, description_row)
    first_data_row = find_first_data_row(raw, date_col, description_row)

    records = []
    for i in range(first_data_row, len(raw)):
        iso_date = _cell_to_iso_date(raw.iat[i, date_col])
        if iso_date is None:
            continue
        raw_value = raw.iat[i, target_col]
        try:
            price = float(raw_value)
        except (TypeError, ValueError):
            continue
        records.append({
            "date": iso_date,
            "commodity": TARGET_COMMODITY_KEY,
            "price_usd": price,
            "unit": unit,
            "source": "Reserve Bank of Australia, Index of Commodity Prices",
            "source_url": SOURCE_URL,
        })

    if not records:
        raise ValueError(
            "Parsed the file but extracted zero coking-coal rows. The "
            "layout likely differs from what this parser assumes -- see "
            "the module docstring's UNVERIFIED LAYOUT note."
        )
    return pd.DataFrame.from_records(records)


def main():
    raw_path = RAW_DIR / f"rba_icp_{date.today().isoformat()}.xlsx"
    if raw_path.exists():
        print(f"Reusing already-downloaded {raw_path}")
    else:
        print(f"Downloading {SOURCE_URL} ...")
        download(raw_path)
        print(f"Saved raw file to {raw_path}")

    df = parse(raw_path)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "commodity_prices_rba_coking.csv"
    df.sort_values("date").to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df["date"].agg(["min", "max", "count"]))
    print(
        f"\nUnit extracted from the file: '{df['unit'].iloc[0]}'. If this "
        "doesn't look like a real price unit (e.g. it's an index-points "
        "figure rather than $/tonne), that's real information this "
        "parser is reporting honestly, not a bug -- check it and update "
        "how this series is labelled in the app if needed."
    )


if __name__ == "__main__":
    main()
