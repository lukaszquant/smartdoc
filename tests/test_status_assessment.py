"""Regression tests for assess_all_statuses — latest-row selection correctness."""

import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_report import assess_all_statuses


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal DataFrame suitable for assess_all_statuses.

    Each row dict must include: marker_id, collected_at, numeric_value.
    Optional: lab_low, lab_high, comparator, marker_label_pl, group, unit,
              collected_date.
    """
    defaults = {
        "comparator": "",
        "marker_label_pl": "Test marker",
        "group": "test_group",
        "unit": "mg/dL",
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        if "collected_date" not in row:
            row["collected_date"] = str(row["collected_at"].date())
        for col in ("lab_low", "lab_high"):
            if col not in row:
                row[col] = np.nan
        full_rows.append(row)
    df = pd.DataFrame(full_rows).sort_values("collected_at").reset_index(drop=True)
    return df


class TestLatestRowSelection(unittest.TestCase):
    """The latest-row selection must use the actual last row per marker,
    without inheriting NaN-skipped values from earlier rows."""

    def test_latest_row_nan_lab_range_not_inherited(self):
        """When the latest row has NaN lab range and an earlier row has a
        populated range, the status assessment must use NaN — not the
        earlier row's range."""
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2025-01-01"),
                "numeric_value": 191.8,
                "lab_low": 115.0,
                "lab_high": 190.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-03-20"),
                "numeric_value": 191.8,
                "lab_low": np.nan,
                "lab_high": np.nan,
            },
        ])
        result = assess_all_statuses(df)
        row = result[result["marker_id"] == "test_marker"].iloc[0]

        # lab_low and lab_high must be NaN from the latest row
        self.assertTrue(math.isnan(row["lab_low"]))
        self.assertTrue(math.isnan(row["lab_high"]))
        # Without lab range, status must NOT be POWYŻEJ NORMY — the bug was
        # that inherited lab_high=190 caused a false lab-basis flag.
        self.assertNotEqual(row["status"], "POWYŻEJ NORMY")

    def test_latest_row_with_lab_range_used_as_is(self):
        """When the latest row has a populated lab range, it should be used
        directly (not mixed with earlier rows)."""
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2025-01-01"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-03-20"),
                "numeric_value": 210.0,
                "lab_low": 110.0,
                "lab_high": 195.0,
            },
        ])
        result = assess_all_statuses(df)
        row = result[result["marker_id"] == "test_marker"].iloc[0]

        self.assertEqual(row["lab_low"], 110.0)
        self.assertEqual(row["lab_high"], 195.0)
        self.assertEqual(row["numeric_value"], 210.0)
        self.assertEqual(row["status"], "POWYŻEJ NORMY")

    def test_single_row_marker(self):
        """A marker with only one row should work identically."""
        df = _make_df([
            {
                "marker_id": "single_marker",
                "collected_at": pd.Timestamp("2026-01-15"),
                "numeric_value": 5.0,
                "lab_low": 1.0,
                "lab_high": 10.0,
            },
        ])
        result = assess_all_statuses(df)
        row = result[result["marker_id"] == "single_marker"].iloc[0]

        self.assertEqual(row["numeric_value"], 5.0)
        self.assertEqual(row["lab_low"], 1.0)
        self.assertEqual(row["lab_high"], 10.0)

    def test_multiple_markers_independent(self):
        """Latest-row selection must be independent per marker_id."""
        df = _make_df([
            {
                "marker_id": "marker_a",
                "collected_at": pd.Timestamp("2025-06-01"),
                "numeric_value": 100.0,
                "lab_low": 50.0,
                "lab_high": 150.0,
            },
            {
                "marker_id": "marker_b",
                "collected_at": pd.Timestamp("2025-06-01"),
                "numeric_value": 200.0,
                "lab_low": 80.0,
                "lab_high": 180.0,
            },
            {
                "marker_id": "marker_a",
                "collected_at": pd.Timestamp("2026-01-01"),
                "numeric_value": 120.0,
                "lab_low": np.nan,
                "lab_high": np.nan,
            },
        ])
        result = assess_all_statuses(df)

        row_a = result[result["marker_id"] == "marker_a"].iloc[0]
        row_b = result[result["marker_id"] == "marker_b"].iloc[0]

        # marker_a: latest row has NaN lab range
        self.assertEqual(row_a["numeric_value"], 120.0)
        self.assertTrue(math.isnan(row_a["lab_low"]))

        # marker_b: only one row, lab range preserved
        self.assertEqual(row_b["numeric_value"], 200.0)
        self.assertEqual(row_b["lab_high"], 180.0)


if __name__ == "__main__":
    unittest.main()
