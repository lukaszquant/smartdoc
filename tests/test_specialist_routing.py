"""Regression tests for specialist routing for Pass 2 groups/markers.

New coverage:
- `koagulacja` group → `internista / hematolog` (INR, wskaźnik protrombiny)
- `autoimmunologia` marker-level overrides:
    - anty_ccp, rf_igm → reumatolog
    - anty_bp180/bp230/enwoplakin/kolagen_vii → dermatolog
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from marker_catalog import GROUP_SPECIALIST, MARKER_SPECIALIST, MARKERS


def _specialist_for(marker_id: str) -> str:
    """Resolve specialist using the same precedence as generate_report:
    marker-level override first, group-level fallback second."""
    override = MARKER_SPECIALIST.get(marker_id)
    if override:
        return override["specialist_pl"]
    group = MARKERS[marker_id]["group"]
    return GROUP_SPECIALIST.get(group, {}).get("specialist_pl", "")


class TestKoagulacjaGroupRouting(unittest.TestCase):

    def test_inr_routes_to_internista_hematolog(self):
        self.assertEqual(MARKERS["inr__direct"]["group"], "koagulacja")
        self.assertEqual(_specialist_for("inr__direct"), "internista / hematolog")

    def test_wskaznik_protrombiny_routes_to_internista_hematolog(self):
        self.assertEqual(
            MARKERS["wskaznik_protrombiny__direct"]["group"], "koagulacja"
        )
        self.assertEqual(
            _specialist_for("wskaznik_protrombiny__direct"),
            "internista / hematolog",
        )


class TestAutoimmunologiaMarkerOverrides(unittest.TestCase):

    def test_anty_ccp_routes_to_reumatolog(self):
        self.assertEqual(_specialist_for("anty_ccp__direct"), "reumatolog")

    def test_rf_igm_routes_to_reumatolog(self):
        self.assertEqual(_specialist_for("rf_igm__direct"), "reumatolog")

    def test_pemphigoid_markers_route_to_dermatolog(self):
        for mid in (
            "anty_bp180__direct",
            "anty_bp230__direct",
            "anty_enwoplakin__direct",
            "anty_kolagen_vii__direct",
        ):
            with self.subTest(marker_id=mid):
                self.assertEqual(_specialist_for(mid), "dermatolog")

    def test_autoimmunologia_group_fallback_exists(self):
        """The group-level fallback must exist for any future markers that
        are added without a marker-level override."""
        self.assertIn("autoimmunologia", GROUP_SPECIALIST)
        self.assertTrue(
            GROUP_SPECIALIST["autoimmunologia"].get("specialist_pl")
        )


if __name__ == "__main__":
    unittest.main()
