"""
Tests the parsing LOGIC of ingest_worldbank.py against a synthetic Excel
file matching the documented Pink Sheet layout — NOT the real file, since
this dev environment cannot reach thedocs.worldbank.org (see the module
docstring in ingest_worldbank.py). This proves the code has no bugs; it
does not prove the real file matches our layout assumptions. Run
ingest_worldbank.py for real, from a normal terminal, to find out.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from data_pipeline.ingest_worldbank import find_header_row, parse, month_label_to_date


def _make_synthetic_pink_sheet(tmp_path: Path) -> Path:
    """Mimics the documented layout: title rows, then a header row of
    '1960M01'-style month labels, then commodity rows."""
    months = ["2026M05", "2026M06", "2026M07"]
    header_row = ["Commodity", *months]
    coal_row = ["Coal, Australian", 136.9, 138.5, 131.9]
    oil_row = ["Crude oil, Brent", 107.5, 85.4, 83.4]
    other_row = ["Some other commodity", 1.0, 2.0, 3.0]

    rows = [
        ["Monthly Prices"],           # row 0: title
        ["($ unless otherwise indicated)"],  # row 1: note
        [],                            # row 2: blank
        header_row,                    # row 3: the real header
        coal_row,
        oil_row,
        other_row,
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "synthetic_pink_sheet.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)
    return path


def test_month_label_to_date():
    assert month_label_to_date("2026M07") == "2026-07-01"


def test_find_header_row(tmp_path):
    path = _make_synthetic_pink_sheet(tmp_path)
    raw = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    assert find_header_row(raw) == 3


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

    # the unrelated row must not leak into our output
    assert "some other commodity" not in df["commodity"].str.lower().values


def test_parse_raises_clearly_if_commodity_missing(tmp_path):
    months = ["2026M05"]
    rows = [
        ["Commodity", *months],
        ["Iron ore", 100.0],
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "no_targets.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Monthly Prices", header=False, index=False)

    with pytest.raises(ValueError, match="zero rows"):
        parse(path)
