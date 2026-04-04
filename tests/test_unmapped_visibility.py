"""Regression tests for unmapped-marker visibility in quality context."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_report import _build_quality_context


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal DataFrame suitable for _build_quality_context."""
    defaults = {
        "comparator": "",
        "quality_flags": "",
        "source_file": "test.csv",
        "collected_date": "2026-01-01",
    }
    full_rows = [{**defaults, **r} for r in rows]
    return pd.DataFrame(full_rows)


class TestUnmappedVisibility(unittest.TestCase):

    def test_unmapped_markers_in_quality_context(self):
        """Unmapped rows (marker_id=NaN) should appear in quality context."""
        df = _make_df([
            {"marker_id": "hdl", "marker_label_pl": "HDL"},
            {"marker_id": np.nan, "marker_label_pl": "Ferrytyna"},
            {"marker_id": np.nan, "marker_label_pl": "Ferrytyna"},
            {"marker_id": np.nan, "marker_label_pl": "Witamina B12"},
        ])
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["unmapped_records"], 3)
        self.assertEqual(ctx["unmapped_marker_count"], 2)
        self.assertIn("Ferrytyna", ctx["unmapped_marker_labels"])
        self.assertIn("Witamina B12", ctx["unmapped_marker_labels"])

    def test_no_unmapped_markers(self):
        """When all rows are mapped, unmapped fields should be zero/empty."""
        df = _make_df([
            {"marker_id": "hdl", "marker_label_pl": "HDL"},
            {"marker_id": "ldl", "marker_label_pl": "LDL"},
        ])
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["unmapped_records"], 0)
        self.assertEqual(ctx["unmapped_marker_count"], 0)
        self.assertEqual(ctx["unmapped_marker_labels"], [])

    def test_unmapped_labels_sorted(self):
        """Unmapped labels should be sorted alphabetically."""
        df = _make_df([
            {"marker_id": np.nan, "marker_label_pl": "Mocznik"},
            {"marker_id": np.nan, "marker_label_pl": "Albumina"},
            {"marker_id": np.nan, "marker_label_pl": "FT3"},
        ])
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["unmapped_marker_labels"],
                         ["Albumina", "FT3", "Mocznik"])

    def test_nan_marker_label_does_not_crash(self):
        """Unmapped row with NaN marker_label_pl should not crash sorted()."""
        df = _make_df([
            {"marker_id": np.nan, "marker_label_pl": "Ferrytyna"},
            {"marker_id": np.nan, "marker_label_pl": np.nan},
        ])
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["unmapped_records"], 2)
        self.assertEqual(ctx["unmapped_marker_count"], 1)
        self.assertEqual(ctx["unmapped_marker_labels"], ["Ferrytyna"])

    def test_all_unmapped(self):
        """When every row is unmapped, quality context should still work."""
        df = _make_df([
            {"marker_id": np.nan, "marker_label_pl": "Albumina"},
            {"marker_id": np.nan, "marker_label_pl": "FT3"},
        ])
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["unmapped_records"], 2)
        self.assertEqual(ctx["unmapped_marker_count"], 2)
        self.assertEqual(ctx["total_records"], 2)
        self.assertEqual(ctx["threshold_markers"], 0)


if __name__ == "__main__":
    unittest.main()
