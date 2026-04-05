"""Regression tests for manual differential vs analyzer differential separation.

Same-day `Gran. Kwasochłonne/Segmentowane/Zasadochłonne` (manual smear) values
must stay separate from `Eozynofile/Neutrofile/Bazofile` (analyzer) percentages
— they are different assays and their values differ.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marker_catalog import resolve_marker_id


class TestManualDifferentialSeparation(unittest.TestCase):

    def test_six_differential_markers_resolve_to_distinct_ids(self):
        """Manual smear labels and analyzer labels must resolve to distinct
        marker_ids so same-day values are preserved independently."""
        pairs = [
            ("Gran. Kwasochłonne", "%"),
            ("Eozynofile", "%"),
            ("Gran. Segmentowane", "%"),
            ("Neutrofile", "%"),
            ("Gran. Zasadochłonne", "%"),
            ("Bazofile", "%"),
        ]
        resolved = [resolve_marker_id(p, u) for p, u in pairs]

        # All six must resolve
        for pair, mid in zip(pairs, resolved):
            self.assertIsNotNone(mid, f"{pair} did not resolve")

        # All six must be distinct
        self.assertEqual(len(set(resolved)), 6, f"Non-distinct ids: {resolved}")

    def test_manual_smear_ids_are_rozmaz_variants(self):
        """Manual smear labels must resolve to _rozmaz_ marker IDs, not to
        analyzer IDs."""
        self.assertEqual(
            resolve_marker_id("Gran. Kwasochłonne", "%"),
            "gran_kwasochlonne_rozmaz__pct",
        )
        self.assertEqual(
            resolve_marker_id("Gran. Segmentowane", "%"),
            "gran_segmentowane_rozmaz__pct",
        )
        self.assertEqual(
            resolve_marker_id("Gran. Zasadochłonne", "%"),
            "gran_zasadochlonne_rozmaz__pct",
        )

    def test_analyzer_labels_do_not_map_to_rozmaz(self):
        """Analyzer labels must not resolve to rozmaz (smear) IDs."""
        for parametr in ("Eozynofile", "Neutrofile", "Bazofile"):
            mid = resolve_marker_id(parametr, "%")
            self.assertIsNotNone(mid)
            self.assertNotIn("rozmaz", mid, f"{parametr} leaked into {mid}")


if __name__ == "__main__":
    unittest.main()
