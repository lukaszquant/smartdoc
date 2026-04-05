"""Regression test for Lp(a) status assessment when lab range is missing.

Before the Pass 2 catalog patch, `Lp(a)` had no `optimal_high`, so a value
of 0.48 g/L with NaN lab range silently fell through to `OK`. The patch
encoded `optimal_high = 0.30 g/L` so missing-range cases assess correctly.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_report import assess_all_statuses


class TestLpaStatusWithoutLabRange(unittest.TestCase):

    def test_lpa_048_above_optimum_when_lab_range_missing(self):
        """Lp(a) 0.48 g/L with NaN lab range must be POWYŻEJ OPT, not OK."""
        df = pd.DataFrame([{
            "marker_id": "lp_a__direct",
            "marker_label_pl": "Lp(a)",
            "group": "lipidy",
            "unit": "g/L",
            "collected_at": pd.Timestamp("2026-01-15"),
            "collected_date": "2026-01-15",
            "numeric_value": 0.48,
            "comparator": "",
            "lab_low": np.nan,
            "lab_high": np.nan,
        }])
        result = assess_all_statuses(df)
        row = result[result["marker_id"] == "lp_a__direct"].iloc[0]

        self.assertEqual(row["status"], "POWYŻEJ OPT")

    def test_lpa_below_optimum_is_ok(self):
        """Lp(a) 0.15 g/L with NaN lab range must be OK (below 0.30 cutoff)."""
        df = pd.DataFrame([{
            "marker_id": "lp_a__direct",
            "marker_label_pl": "Lp(a)",
            "group": "lipidy",
            "unit": "g/L",
            "collected_at": pd.Timestamp("2026-01-15"),
            "collected_date": "2026-01-15",
            "numeric_value": 0.15,
            "comparator": "",
            "lab_low": np.nan,
            "lab_high": np.nan,
        }])
        result = assess_all_statuses(df)
        row = result[result["marker_id"] == "lp_a__direct"].iloc[0]

        self.assertEqual(row["status"], "OK")


if __name__ == "__main__":
    unittest.main()
