"""Regression tests for NRBC unit-specific alias resolution.

NRBC is reported in two distinct units that correspond to two existing
marker IDs: "%" -> nrbc__pct, "tys/µl" -> nrbc__abs. No standalone
nrbc__direct exists — unit routing is the sole disambiguator.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marker_catalog import resolve_marker_id


class TestNrbcUnitRouting(unittest.TestCase):

    def test_nrbc_percent_routes_to_pct(self):
        self.assertEqual(resolve_marker_id("NRBC", "%"), "nrbc__pct")

    def test_nrbc_absolute_routes_to_abs(self):
        self.assertEqual(resolve_marker_id("NRBC", "tys/µl"), "nrbc__abs")

    def test_nrbc_hash_wildcard_still_resolves(self):
        """Existing NRBC# (absolute count) alias keeps working."""
        mid = resolve_marker_id("NRBC#", "tys/µl")
        self.assertIsNotNone(mid)
        self.assertEqual(mid, "nrbc__abs")

    def test_nrbc_percent_wildcard_still_resolves(self):
        """Existing NRBC% (percentage) alias keeps working."""
        mid = resolve_marker_id("NRBC%", "%")
        self.assertIsNotNone(mid)
        self.assertEqual(mid, "nrbc__pct")


if __name__ == "__main__":
    unittest.main()
