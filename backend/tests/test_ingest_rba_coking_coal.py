"""
Tests the parsing LOGIC of ingest_rba_coking_coal.py against a synthetic
Excel file matching RBA's well-documented standard statistical-table
convention (a metadata block with one label per row in column A --
Description / Frequency / Type / Unit / Source / Publication date /
Series ID -- then dated data rows below). UNLIKE test_ingest_worldbank.py,
this layout has NOT been confirmed against the real i02hist.xlsx file --
Claude's execution environments cannot reach rba.gov.au (see DECISIONS.md
#10, #23). These tests prove the defensive label/date-searching logic
works on a plausible instance of the documented convention; they do not
prove the real file matches it. The user's first real run is what
actually confirms or corrects this -- see the module docstring.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from data_pipeline.ingest_rba_coking_coal import (
    find_date_column,
    find_first_data_row,
    find_row_by_label,
    find_target_column,
    find_unit_label,
    parse,
)


def _make_synthetic_rba_table(tmp_path: Path, unit="$US/tonne") -> Path:
    """Mimics RBA's standard table shape: a title row, a metadata block
    (Description/Frequency/Type/Unit/Source/Publication date/Series ID,
    one series per column), a blank separator row, then dated data rows
    with real datetime values in column A."""
    import datetime as dt

    rows = [
        ["Index of Commodity Prices - I2", None, None, None],
        ["Description", "Total, SDR", "Coking coal", "Thermal coal"],
        ["Frequency", "Monthly", "Monthly", "Monthly"],
        ["Type", "Original", "Original", "Original"],
        ["Unit", "Index", unit, unit],
        ["Source", "RBA", "RBA", "RBA"],
        ["Publication date", "2026-08-04", "2026-08-04", "2026-08-04"],
        ["Series ID", "GRCPBCSDR", "GRCPBCCOK", "GRCPBCTHM"],
        [None, None, None, None],
        [dt.datetime(2026, 5, 1), 210.4, 205.0, 118.5],
        [dt.datetime(2026, 6, 1), 208.9, 198.3, 116.2],
        [dt.datetime(2026, 7, 1), 212.1, 214.9, 119.8],
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "synthetic_rba_icp.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", header=False, index=False)
    return path


def test_find_row_by_label(tmp_path):
    path = _make_synthetic_rba_table(tmp_path)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    assert find_row_by_label(raw, "Description") == 1
    assert find_row_by_label(raw, "Series ID") == 7


def test_find_row_by_label_raises_clearly_if_missing(tmp_path):
    path = _make_synthetic_rba_table(tmp_path)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    with pytest.raises(ValueError, match="Could not find a row labelled"):
        find_row_by_label(raw, "Not A Real Label")


def test_find_target_column(tmp_path):
    path = _make_synthetic_rba_table(tmp_path)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    description_row = find_row_by_label(raw, "Description")
    assert find_target_column(raw, description_row) == 2  # "Coking coal" column


def test_find_target_column_raises_clearly_if_absent(tmp_path):
    # A table with no coking-coal column at all (e.g. only thermal coal).
    rows = [
        ["Description", "Thermal coal"],
        ["Unit", "$US/tonne"],
        [None, None],
    ]
    df = pd.DataFrame(rows)
    path = tmp_path / "no_coking_coal.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", header=False, index=False)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    description_row = find_row_by_label(raw, "Description")
    with pytest.raises(ValueError, match="no column"):
        find_target_column(raw, description_row)


def test_find_unit_label(tmp_path):
    path = _make_synthetic_rba_table(tmp_path, unit="$US/tonne")
    raw = pd.read_excel(path, sheet_name=0, header=None)
    description_row = find_row_by_label(raw, "Description")
    target_col = find_target_column(raw, description_row)
    assert find_unit_label(raw, target_col) == "$US/tonne"


def test_find_date_column_and_first_data_row(tmp_path):
    path = _make_synthetic_rba_table(tmp_path)
    raw = pd.read_excel(path, sheet_name=0, header=None)
    description_row = find_row_by_label(raw, "Description")
    date_col = find_date_column(raw, description_row)
    assert date_col == 0
    assert find_first_data_row(raw, date_col, description_row) == 9


def test_parse_extracts_coking_coal(tmp_path):
    path = _make_synthetic_rba_table(tmp_path)
    df = parse(path)

    assert set(df["commodity"].unique()) == {"coking_coal"}
    assert list(df.sort_values("date")["price_usd"]) == [205.0, 198.3, 214.9]
    assert list(df.sort_values("date")["date"]) == [
        "2026-05-01", "2026-06-01", "2026-07-01",
    ]
    # "Total, SDR" and "Thermal coal" columns must not leak into the output
    assert len(df) == 3


def test_parse_reports_whatever_unit_the_file_actually_states(tmp_path):
    # If the real file turns out to hold an index-points figure rather than
    # a $/tonne price, this parser must report that honestly, not silently
    # relabel it as a price unit.
    path = _make_synthetic_rba_table(tmp_path, unit="Index")
    df = parse(path)
    assert (df["unit"] == "Index").all()


def test_parse_raises_clearly_if_description_row_missing(tmp_path):
    rows = [["Just some unrelated data", 1, 2, 3]]
    df = pd.DataFrame(rows)
    path = tmp_path / "no_description_row.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Data", header=False, index=False)

    with pytest.raises(ValueError, match="Could not find a row labelled"):
        parse(path)
