"""Regression tests for same-day conflict classification (status-flip detection)."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_report import (
    _build_quality_context,
    consolidate_measurements,
)


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal DataFrame suitable for consolidate_measurements."""
    defaults = {
        "comparator": "",
        "quality_flags": "",
        "source_file": "test.csv",
        "source_order_id": "ORD-001",
        "source_origin": "csv",
        "marker_label_pl": "Test marker",
    }
    full_rows = []
    for r in rows:
        row = {**defaults, **r}
        if "collected_date" not in row:
            row["collected_date"] = str(row["collected_at"].date())
        for col in ("lab_low", "lab_high", "raw_value"):
            if col not in row:
                row[col] = row.get("numeric_value", np.nan)
        full_rows.append(row)
    df = pd.DataFrame(full_rows).sort_values("collected_at").reset_index(drop=True)
    return df


class TestSameDayConflictClassification(unittest.TestCase):
    """Conflicts should be classified as safe or status-flipping."""

    def test_status_flip_conflict_flagged(self):
        """Two same-day values that produce different statuses → status flip."""
        # Value 150 is within lab range (100-200) → OK
        # Value 250 is above lab range → POWYŻEJ NORMY
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 250.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        result_df, stats = consolidate_measurements(df)

        # Should have exactly one conflict, and it's a status flip
        self.assertEqual(len(stats["conflict_details"]), 1)
        conflict = stats["conflict_details"][0]
        self.assertTrue(conflict["is_status_flip"])
        self.assertIn("OK", conflict["statuses"])
        self.assertIn("POWYŻEJ NORMY", conflict["statuses"])

        # The kept row should have the status_flip flag
        row = result_df[result_df["marker_id"] == "test_marker"].iloc[0]
        flags = row["quality_flags"].split(";")
        self.assertIn("same_day_conflict_status_flip", flags)

    def test_safe_conflict_no_status_flip(self):
        """Two same-day values that produce the same status → no flip."""
        # Both 120 and 130 are within lab range (100-200) → both OK
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 120.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 130.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        result_df, stats = consolidate_measurements(df)

        self.assertEqual(len(stats["conflict_details"]), 1)
        conflict = stats["conflict_details"][0]
        self.assertFalse(conflict["is_status_flip"])
        self.assertEqual(conflict["statuses"], ["OK"])

        # The kept row should have plain conflict flag, not the flip variant
        row = result_df[result_df["marker_id"] == "test_marker"].iloc[0]
        flags = row["quality_flags"].split(";")
        self.assertIn("same_day_conflict", flags)
        self.assertNotIn("same_day_conflict_status_flip", flags)

    def test_same_day_repeat_not_flagged_as_conflict(self):
        """Identical values on the same day → repeat, not conflict."""
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        _, stats = consolidate_measurements(df)

        self.assertEqual(len(stats["conflict_details"]), 0)
        self.assertEqual(stats["n_same_day_repeat_removed"], 1)

    def test_conflict_details_include_source_files(self):
        """Conflict details should include source file metadata."""
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
                "source_file": "panel_a.csv",
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 250.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
                "source_file": "panel_b.csv",
            },
        ])
        _, stats = consolidate_measurements(df)

        conflict = stats["conflict_details"][0]
        self.assertIn("panel_a.csv", conflict["source_files"])
        self.assertIn("panel_b.csv", conflict["source_files"])

    def test_conflict_keeps_latest_timestamp_row(self):
        """For both safe and unsafe conflicts, the latest-timestamp row is kept."""
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 250.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        result_df, stats = consolidate_measurements(df)

        # Only one row remains
        marker_rows = result_df[result_df["marker_id"] == "test_marker"]
        self.assertEqual(len(marker_rows), 1)
        # It's the latest-timestamp value
        self.assertEqual(marker_rows.iloc[0]["numeric_value"], 250.0)

    def test_multiple_markers_independent_conflict_classification(self):
        """Conflict classification must be independent per marker."""
        df = _make_df([
            # marker_a: status flip (OK vs POWYŻEJ NORMY)
            {
                "marker_id": "marker_a",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 150.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "marker_a",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 250.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            # marker_b: safe conflict (both OK)
            {
                "marker_id": "marker_b",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 120.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "marker_b",
                "collected_at": pd.Timestamp("2026-01-15 14:00"),
                "numeric_value": 130.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        result_df, stats = consolidate_measurements(df)

        self.assertEqual(len(stats["conflict_details"]), 2)
        by_marker = {c["marker_id"]: c for c in stats["conflict_details"]}

        self.assertTrue(by_marker["marker_a"]["is_status_flip"])
        self.assertFalse(by_marker["marker_b"]["is_status_flip"])

        # Check flags on kept rows
        row_a = result_df[result_df["marker_id"] == "marker_a"].iloc[0]
        row_b = result_df[result_df["marker_id"] == "marker_b"].iloc[0]
        flags_a = row_a["quality_flags"].split(";")
        flags_b = row_b["quality_flags"].split(";")
        self.assertIn("same_day_conflict_status_flip", flags_a)
        self.assertNotIn("same_day_conflict_status_flip", flags_b)


    def test_three_way_conflict_with_status_flip(self):
        """Three values on the same day — two share a status, one differs."""
        # 120 and 180 are within lab range (100-200) → OK
        # 250 is above lab range → POWYŻEJ NORMY
        df = _make_df([
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 08:00"),
                "numeric_value": 120.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 12:00"),
                "numeric_value": 180.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
            {
                "marker_id": "test_marker",
                "collected_at": pd.Timestamp("2026-01-15 16:00"),
                "numeric_value": 250.0,
                "lab_low": 100.0,
                "lab_high": 200.0,
            },
        ])
        result_df, stats = consolidate_measurements(df)

        self.assertEqual(len(stats["conflict_details"]), 1)
        conflict = stats["conflict_details"][0]
        self.assertTrue(conflict["is_status_flip"])
        self.assertEqual(len(conflict["numeric_values"]), 3)
        # Kept the latest (16:00) row
        self.assertEqual(conflict["kept_value"], 250.0)
        # Two distinct statuses
        self.assertIn("OK", conflict["statuses"])
        self.assertIn("POWYŻEJ NORMY", conflict["statuses"])


class TestQualityContextConflicts(unittest.TestCase):
    """Quality context should expose conflict data from dedup_stats."""

    def _make_simple_df(self):
        return pd.DataFrame([{
            "quality_flags": "",
            "comparator": "",
            "marker_id": "hdl",
            "marker_label_pl": "HDL",
            "source_file": "test.csv",
            "collected_date": "2026-01-01",
        }])

    def test_status_flip_conflicts_in_quality_context(self):
        """Status-flip conflicts should appear in quality context."""
        df = self._make_simple_df()
        dedup_stats = {
            "conflict_details": [
                {
                    "marker_id": "test_marker",
                    "date": "2026-01-15",
                    "numeric_values": [150.0, 250.0],
                    "kept_value": 250.0,
                    "n_records": 2,
                    "statuses": ["OK", "POWYŻEJ NORMY"],
                    "is_status_flip": True,
                    "source_files": ["a.csv", "b.csv"],
                },
                {
                    "marker_id": "safe_marker",
                    "date": "2026-01-15",
                    "numeric_values": [120.0, 130.0],
                    "kept_value": 130.0,
                    "n_records": 2,
                    "statuses": ["OK"],
                    "is_status_flip": False,
                    "source_files": ["a.csv"],
                },
            ],
        }
        ctx = _build_quality_context(df, dedup_stats)

        self.assertEqual(ctx["conflict_count"], 2)
        self.assertEqual(len(ctx["status_flip_conflicts"]), 1)
        self.assertEqual(ctx["status_flip_conflicts"][0]["marker_id"], "test_marker")

    def test_no_conflicts_in_quality_context(self):
        """When no dedup_stats provided, conflict fields should be zero/empty."""
        df = self._make_simple_df()
        ctx = _build_quality_context(df)

        self.assertEqual(ctx["conflict_count"], 0)
        self.assertEqual(ctx["status_flip_conflicts"], [])

    def test_no_status_flips(self):
        """When all conflicts are safe, status_flip_conflicts should be empty."""
        df = self._make_simple_df()
        dedup_stats = {
            "conflict_details": [
                {
                    "marker_id": "safe_marker",
                    "date": "2026-01-15",
                    "numeric_values": [120.0, 130.0],
                    "kept_value": 130.0,
                    "n_records": 2,
                    "statuses": ["OK"],
                    "is_status_flip": False,
                    "source_files": ["a.csv"],
                },
            ],
        }
        ctx = _build_quality_context(df, dedup_stats)

        self.assertEqual(ctx["conflict_count"], 1)
        self.assertEqual(ctx["status_flip_conflicts"], [])


if __name__ == "__main__":
    unittest.main()
