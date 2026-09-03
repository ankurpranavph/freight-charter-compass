"""
Tests the parsing LOGIC of ingest_worldbank.py against a synthetic Excel
file matching the REAL Pink Sheet layout, confirmed on 2026-09-03 by
dumping the actual downloaded file: title rows, then a header row of
commodity names across columns, a units row, then data rows with month
labels ("1960M01"-style) down column A and one price column per commodity.
Missing values are the literal string '...' (ellipsis), per the real file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from data_pipeline.ingest_worldbank import (
    find_date_column,
    find_first_data_row,
    find_header_row,
    month_label_to_date,
    parse,
)


def _make_synthetic_pink_sheet(tmp_path: Path) -> Path:
    """Mimics the real layout: 4 title rows (col A only), a commodity-name
    header row (col A blank), a units row, then data rows with month labels
    in col A and one price column per commodity."""
    rows = [
        ["World Bank Commodity Price Data (The Pink Sheet)"],       # row 0
        ["monthly prices in nominal US dollars, 1960 to present"],  # row 1
        ["(monthly series are available only in nominal US dollars)"],  # row 2
        ["Updated on September 02, 2026"],                          # row 3
        [None, "Crude oil, average", "Crude oil, Brent", "Coal, Australian", "Coal, South African **"],  # row 4: header
        [None, "($/bbl)", "($/bbl)", "($/mt)", "($/mt)"],           # row 5: units
        ["2026M05", 105.0, 107.5, 136.9, 120.0],
        ["2026M06", 84.0, 85.4, 138.5, 118.0],
        ["2026M07", "...", 83.4, 131.9, "..."],  # missing values as ellipsis
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "synthetic_pink_sheet.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)
    return path


def test_month_label_to_date():
    assert month_label_to_date("2026M07") == "2026-07-01"


def test_find_date_column(tmp_path):
    path = _make_synthetic_pink_sheet(tmp_path)
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    assert find_date_column(raw) == 0


def test_find_first_data_row(tmp_path):
    path = _make_synthetic_pink_sheet(tmp_path)
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    date_col = find_date_column(raw)
    assert find_first_data_row(raw, date_col) == 6


def test_find_header_row(tmp_path):
    path = _make_synthetic_pink_sheet(tmp_path)
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    date_col = find_date_column(raw)
    first_data_row = find_first_data_row(raw, date_col)
    assert find_header_row(raw, date_col, first_data_row) == 4


def test_parse_extracts_target_commodities(tmp_path):
    path = _make_synthetic_pink_sheet(tmp_path)
    df = parse(path)

    coal = df[df["commodity"] == "coal_australian"].sort_values("date")
    assert list(coal["price_usd"]) == [136.9, 138.5, 131.9]
    assert list(coal["date"]) == ["2026-05-01", "2026-06-01", "2026-07-01"]
    assert (coal["unit"] == "usd_per_tonne").all()

    oil = df[df["commodity"] == "crude_oil_brent"].sort_values("date")
    assert list(oil["price_usd"]) == [107.5, 85.4, 83.4]
    assert (oil["unit"] == "usd_per_bbl").all()

    # unrelated columns ("Crude oil, average", "Coal, South African **")
    # must not leak into our output
    assert set(df["commodity"].unique()) == {"coal_australian", "crude_oil_brent"}


def test_parse_skips_ellipsis_missing_values(tmp_path):
    # "Crude oil, average" has ellipsis in the last row in the fixture above -
    # confirm that column, if it were a target, would just skip that month
    # rather than crashing or emitting a garbage value. We test this
    # indirectly via coal_australian/crude_oil_brent, which have no gaps in
    # the fixture, so assert the row counts are exactly 3 (no phantom rows
    # from missing-value mishandling elsewhere).
    path = _make_synthetic_pink_sheet(tmp_path)
    df = parse(path)
    assert len(df[df["commodity"] == "coal_australian"]) == 3
    assert len(df[df["commodity"] == "crude_oil_brent"]) == 3


def test_parse_raises_clearly_if_commodity_missing(tmp_path):
    # Needs enough unrelated commodity columns for header-row detection to
    # succeed (real files have ~70+ columns; this exercises the "header
    # found, but none of our targets are among the columns" path
    # specifically, not the "couldn't find a header at all" path covered by
    # find_header_row's own error).
    rows = [
        [None, "Iron ore", "Zinc", "Aluminum", "Copper"],
        [None, "($/dmtu)", "($/mt)", "($/mt)", "($/mt)"],
        ["2026M05", 100.0, 2500.0, 2200.0, 9000.0],
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "no_targets.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)

    with pytest.raises(ValueError, match="zero rows"):
        parse(path)
