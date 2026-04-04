"""
Marker catalog — alias map, canonical IDs, marker metadata, and optimal ranges.

This module is the single source of truth for mapping raw CSV `Parametr` names
to canonical marker identifiers, and for defining marker groups, expression
types, units, optimal ranges, and evidence metadata.

Design decisions
----------------
* marker_id  = canonical_name + "__" + expression_type   (e.g. "eozynofile__pct")
  The double-underscore avoids collisions with marker names that contain
  single underscores or hyphens.
* expression_type is one of: abs, pct, ratio, calculated, direct
  - abs:        absolute count (tys/µl, mln/µl)
  - pct:        percentage (%)
  - ratio:      ratio / index (e.g. fPSA/PSA)
  - calculated: derived value (eGFR)
  - direct:     the only expression form for this marker (most biochem markers)
* The alias map resolves (Parametr, unit_hint) → marker_id.  unit_hint is the
  unit string stripped from the Wynik column.  It disambiguates markers like
  "Eozynofile" which appear both as tys/µl (abs) and % (pct).

Optimal ranges (Phase 3)
-------------------------
* Each marker entry may contain `optimal_low` and `optimal_high`:
  - Both None → no optimal range defined (assess against lab only)
  - optimal_low only → lower-bounded (e.g. HDL > 60)
  - optimal_high only → upper-bounded (e.g. LDL < 100)
  - Both set → two-sided range (e.g. TSH 0.5-2.0)
* source_type: LAB, GUIDELINE, HEURISTIC, EXPLORATORY (per PLAN_ANALIZY.md §5)
* evidence_level: "high", "moderate", "low" — quality of evidence for optimal
* source_label: specific reference (e.g. "ESC/EAS 2021")
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Marker groups  (keys used throughout the report)
# ---------------------------------------------------------------------------
GROUPS = {
    "lipidy":       "Układ krążenia / Lipidogram",
    "weglowodany":  "Gospodarka węglowodanowa",
    "hormony":      "Hormony płciowe i przysadka",
    "tarczyca":     "Tarczyca",
    "prostata":     "Prostata",
    "watroba":      "Wątroba",
    "nerki":        "Nerki",
    "zapalenie":    "Stan zapalny",
    "mineraly":     "Minerały i elektrolity",
    "witaminy":     "Witaminy",
    "metale":       "Metale ciężkie",
    "kwasy_tluszczowe": "Kwasy tłuszczowe / Omega",
    "morfologia":   "Morfologia",
}

# ---------------------------------------------------------------------------
# Specialist routing — marker-level overrides + group-level fallback
# ---------------------------------------------------------------------------

# Marker-level overrides for heterogeneous groups (e.g. lipidy contains
# D-dimer, homocysteina, hsCRP alongside actual lipid markers).
MARKER_SPECIALIST: dict[str, dict] = {
    "homocysteina__direct": {
        "specialist_pl": "internista",
        "additional_tests": [
            {"label_pl": "Witamina B12", "filter_aliases": ["Witamina B12", "B12"]},
            {"label_pl": "Kwas foliowy", "filter_aliases": ["Kwas foliowy", "Folian"]},
            {"label_pl": "Witamina B6", "filter_aliases": ["Witamina B6", "B6"]},
        ],
    },
    "d_dimer__direct": {
        "specialist_pl": "internista / angiolog",
        "additional_tests": [
            {"label_pl": "Fibrynogen", "filter_aliases": ["Fibrynogen"]},
            {"label_pl": "USG żył kończyn dolnych"},
        ],
    },
    "hscrp__direct": {
        "specialist_pl": "internista / reumatolog",
        "additional_tests": [
            {"label_pl": "OB (odczyn Biernackiego)", "filter_aliases": ["OB", "Odczyn Biernackiego", "OB (odczyn Biernackiego)"]},
            {"label_pl": "Prokalcytonina", "filter_aliases": ["Prokalcytonina"]},
        ],
    },
}

# Group-level fallback: used when no marker-level override exists.
# Groups omitted here keep generic "Omówić z lekarzem" with no specialist.
GROUP_SPECIALIST: dict[str, dict] = {
    "lipidy": {
        "specialist_pl": "kardiolog",
        "additional_tests": [
            {"label_pl": "Lp(a) — lipoproteina(a)", "filter_aliases": ["Lp(a)", "Lipoproteina(a)", "Lp(a) — lipoproteina(a)"]},
            {"label_pl": "ApoA1", "filter_aliases": ["ApoA1", "Apo A1"]},
            {"label_pl": "Profil lipidowy rozszerzony (frakcje LDL)"},
        ],
    },
    "weglowodany": {
        "specialist_pl": "diabetolog / endokrynolog",
        "additional_tests": [
            {"label_pl": "Insulina na czczo", "filter_aliases": ["Insulina", "Insulina na czczo"]},
            {"label_pl": "HOMA-IR (obliczeniowy)", "filter_aliases": ["HOMA-IR"]},
            {"label_pl": "Peptyd C", "filter_aliases": ["Peptyd C"]},
            {"label_pl": "OGTT (test obciążenia glukozą)"},
        ],
    },
    "hormony": {
        "specialist_pl": "endokrynolog / androlog",
        "additional_tests": [
            {"label_pl": "Estradiol", "filter_aliases": ["Estradiol"]},
            {"label_pl": "DHEA-S", "filter_aliases": ["DHEA-S", "DHEAS"]},
            {"label_pl": "Kortyzol poranny", "filter_aliases": ["Kortyzol", "Kortyzol poranny"]},
        ],
    },
    "tarczyca": {
        "specialist_pl": "endokrynolog",
        "additional_tests": [
            {"label_pl": "FT3", "filter_aliases": ["FT3", "fT3"]},
            {"label_pl": "Anty-TPO", "filter_aliases": ["Anty-TPO", "Anty TPO"]},
            {"label_pl": "Anty-TG", "filter_aliases": ["Anty-TG", "Anty TG"]},
            {"label_pl": "USG tarczycy"},
        ],
    },
    "prostata": {
        "specialist_pl": "urolog",
        "additional_tests": [
            {"label_pl": "mpMRI prostaty (przy podwyższonym PSA)"},
            {"label_pl": "PHI (Prostate Health Index)"},
        ],
    },
    "watroba": {
        "specialist_pl": "gastroenterolog / hepatolog",
        "additional_tests": [
            {"label_pl": "Albumina", "filter_aliases": ["Albumina"]},
            {"label_pl": "Bilirubina bezpośrednia", "filter_aliases": ["Bilirubina bezpośrednia"]},
            {"label_pl": "Bilirubina pośrednia", "filter_aliases": ["Bilirubina pośrednia"]},
            {"label_pl": "USG jamy brzusznej"},
            {"label_pl": "FibroScan / FIB-4 (przy przewlekłym podwyższeniu)"},
        ],
    },
    "nerki": {
        "specialist_pl": "nefrolog",
        "additional_tests": [
            {"label_pl": "Cystatyna C", "filter_aliases": ["Cystatyna C"]},
            {"label_pl": "Badanie ogólne moczu"},
            {"label_pl": "ACR (albumina/kreatynina w moczu)"},
        ],
    },
    "zapalenie": {
        "specialist_pl": "internista / reumatolog",
        "additional_tests": [
            {"label_pl": "OB (odczyn Biernackiego)", "filter_aliases": ["OB", "Odczyn Biernackiego", "OB (odczyn Biernackiego)"]},
            {"label_pl": "Prokalcytonina", "filter_aliases": ["Prokalcytonina"]},
            {"label_pl": "Ferrytyna", "filter_aliases": ["Ferrytyna"]},
        ],
    },
    "metale": {
        "specialist_pl": "toksykolog / internista",
        "additional_tests": [
            {"label_pl": "Metale ciężkie w moczu (prowokowany)"},
        ],
    },
    "morfologia": {
        "specialist_pl": "hematolog",
        "additional_tests": [
            {"label_pl": "Rozmaz krwi obwodowej (manualny)"},
            {"label_pl": "Retikulocyty", "filter_aliases": ["Retikulocyty"]},
            {"label_pl": "Ferrytyna", "filter_aliases": ["Ferrytyna"]},
            {"label_pl": "Żelazo", "marker_id": "zelazo__direct"},
            {"label_pl": "TIBC", "filter_aliases": ["TIBC"]},
            {"label_pl": "Witamina B12", "filter_aliases": ["Witamina B12", "B12"]},
            {"label_pl": "Kwas foliowy", "filter_aliases": ["Kwas foliowy", "Folian"]},
        ],
    },
}

# Catalog-wide review date
CATALOG_LAST_REVIEWED = "2026-04-03"

# ---------------------------------------------------------------------------
# Canonical marker definitions
# ---------------------------------------------------------------------------
# Each entry:  marker_id → dict with label_pl, group, unit, expression_type,
#   optimal_low, optimal_high, source_type, source_label, evidence_level, notes
# ---------------------------------------------------------------------------

MARKERS: dict[str, dict] = {
    # ======================================================================
    # Lipidy
    # ======================================================================
    "cholesterol_calkowity__direct": {
        "label_pl": "Cholesterol całkowity", "group": "lipidy",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 180.0,
        "source_type": "GUIDELINE", "source_label": "ESC/EAS 2021",
        "evidence_level": "high",
        "notes": "",
    },
    "cholesterol_hdl__direct": {
        "label_pl": "Cholesterol HDL", "group": "lipidy",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": 60.0, "optimal_high": None,
        "source_type": "GUIDELINE", "source_label": "ESC/EAS 2021",
        "evidence_level": "high",
        "notes": "",
    },
    "cholesterol_ldl__direct": {
        "label_pl": "Cholesterol LDL", "group": "lipidy",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 100.0,
        "source_type": "GUIDELINE", "source_label": "ESC/EAS 2021",
        "evidence_level": "high",
        "notes": "Dla osób bez czynników ryzyka CV; przy czynnikach <70",
    },
    "cholesterol_nie_hdl__direct": {
        "label_pl": "Cholesterol nie-HDL", "group": "lipidy",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 100.0,
        "source_type": "GUIDELINE", "source_label": "ESC/EAS 2021",
        "evidence_level": "high",
        "notes": "",
    },
    "triglicerydy__direct": {
        "label_pl": "Triglicerydy", "group": "lipidy",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 80.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab <100-150; optymalnie <80 wg podejścia prewencyjnego",
    },
    "apo_b__direct": {
        "label_pl": "Apo B", "group": "lipidy",
        "unit": "g/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 0.80,
        "source_type": "GUIDELINE", "source_label": "ESC/EAS 2021",
        "evidence_level": "high",
        "notes": "Cel <0.80 g/l dla niskiego ryzyka CV; <0.65 dla wysokiego",
    },
    "homocysteina__direct": {
        "label_pl": "Homocysteina", "group": "lipidy",
        "unit": "µmol/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 10.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Marker metabolizmu B6/B12/folianów; podwyższona = ryzyko CV",
    },
    "d_dimer__direct": {
        "label_pl": "D-dimer", "group": "lipidy",
        "unit": "µg/ml", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 0.5,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "",
    },
    "hscrp__direct": {
        "label_pl": "CRP wysokiej czułości", "group": "lipidy",
        "unit": "mg/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 1.0,
        "source_type": "GUIDELINE", "source_label": "AHA/CDC (Ridker)",
        "evidence_level": "high",
        "notes": "hsCRP <1.0 = niskie ryzyko CV",
    },

    # ======================================================================
    # Węglowodany
    # ======================================================================
    "glukoza__direct": {
        "label_pl": "Glukoza", "group": "weglowodany",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 90.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Na czczo; norma lab 70-99",
    },
    "hba1c__direct": {
        "label_pl": "Hemoglobina glikowana", "group": "weglowodany",
        "unit": "%", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 5.4,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab <6%; 5.7-6.4% = prediabetes wg ADA",
    },

    # ======================================================================
    # Hormony płciowe i przysadka
    # ======================================================================
    "testosteron__direct": {
        "label_pl": "Testosteron", "group": "hormony",
        "unit": "ng/dl", "expression_type": "direct",
        "optimal_low": 500.0, "optimal_high": 900.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Zakres optymalny dla mężczyzny 40-50 lat z aktywnym stylem życia",
    },
    "testosteron_wolny__direct": {
        "label_pl": "Testosteron wolny", "group": "hormony",
        "unit": "pg/ml", "expression_type": "direct",
        "optimal_low": 15.0, "optimal_high": 35.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "shbg__direct": {
        "label_pl": "SHBG", "group": "hormony",
        "unit": "nmol/l", "expression_type": "direct",
        "optimal_low": 20.0, "optimal_high": 50.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Wysokie SHBG obniża biodostępność testosteronu",
    },
    "lh__direct": {
        "label_pl": "LH", "group": "hormony",
        "unit": "mIU/ml", "expression_type": "direct",
        "optimal_low": 2.0, "optimal_high": 8.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "low",
        "notes": "Zbliżony do normy lab (1.7-8.6)",
    },
    "fsh__direct": {
        "label_pl": "FSH", "group": "hormony",
        "unit": "mIU/ml", "expression_type": "direct",
        "optimal_low": 1.5, "optimal_high": 8.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "low",
        "notes": "Zbliżony do normy lab (1.5-12.4)",
    },
    "prolaktyna__direct": {
        "label_pl": "Prolaktyna", "group": "hormony",
        "unit": "mIU/l", "expression_type": "direct",
        "optimal_low": 85.0, "optimal_high": 300.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "low",
        "notes": "Zbliżony do normy lab (86-324)",
    },
    "igf1__direct": {
        "label_pl": "IGF-1", "group": "hormony",
        "unit": "ng/ml", "expression_type": "direct",
        "optimal_low": 120.0, "optimal_high": 200.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Zależny od wieku; niski IGF-1 = sygnał niedoboru GH lub żywieniowy",
    },

    # ======================================================================
    # Tarczyca
    # ======================================================================
    "tsh__direct": {
        "label_pl": "TSH", "group": "tarczyca",
        "unit": "µIU/ml", "expression_type": "direct",
        "optimal_low": 0.5, "optimal_high": 2.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna / ATA 2017",
        "evidence_level": "moderate",
        "notes": "ATA ref 0.45-4.12; zakres 0.5-2.0 preferowany w medycynie funkcjonalnej",
    },
    "ft4__direct": {
        "label_pl": "FT4", "group": "tarczyca",
        "unit": "ng/dl", "expression_type": "direct",
        "optimal_low": 1.1, "optimal_high": 1.5,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Górna połowa normy lab (0.92-1.68)",
    },

    # ======================================================================
    # Prostata
    # ======================================================================
    "psa__direct": {
        "label_pl": "PSA", "group": "prostata",
        "unit": "ng/ml", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 1.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab <2 dla mężczyzn <50 lat",
    },
    "psa_wolny__direct": {
        "label_pl": "PSA wolny", "group": "prostata",
        "unit": "ng/ml", "expression_type": "direct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z PSA i wskaźnikiem fPSA/PSA",
    },
    "psa_wskaznik__ratio": {
        "label_pl": "PSA - wskaźnik (fPSA/PSA)", "group": "prostata",
        "unit": "%", "expression_type": "ratio",
        "optimal_low": 25.0, "optimal_high": None,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Wyższy wskaźnik = mniejsze ryzyko nowotworu",
    },

    # ======================================================================
    # Wątroba
    # ======================================================================
    "alt__direct": {
        "label_pl": "ALT", "group": "watroba",
        "unit": "U/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 25.0,
        "source_type": "HEURISTIC", "source_label": "Prati et al. 2002 / medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab <41; optymalnie <25 wg Prati",
    },
    "ast__direct": {
        "label_pl": "AST", "group": "watroba",
        "unit": "U/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 25.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "bilirubina__direct": {
        "label_pl": "Bilirubina całkowita", "group": "watroba",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": 0.3, "optimal_high": 1.0,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "Lekko podwyższona bilirubina (Gilbert) może być ochronna",
    },
    "ggtp__direct": {
        "label_pl": "GGTP", "group": "watroba",
        "unit": "U/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 30.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 10-71; optymalnie <30",
    },
    "fosfataza_zasadowa__direct": {
        "label_pl": "Fosfataza zasadowa", "group": "watroba",
        "unit": "U/l", "expression_type": "direct",
        "optimal_low": 40.0, "optimal_high": 100.0,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "",
    },

    # ======================================================================
    # Nerki
    # ======================================================================
    "kreatynina__direct": {
        "label_pl": "Kreatynina", "group": "nerki",
        "unit": "mg/dl", "expression_type": "direct",
        "optimal_low": 0.8, "optimal_high": 1.1,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "Zależna od masy mięśniowej",
    },
    "egfr__calculated": {
        "label_pl": "eGFR", "group": "nerki",
        "unit": "ml/min/1,73m2", "expression_type": "calculated",
        "optimal_low": 90.0, "optimal_high": None,
        "source_type": "GUIDELINE", "source_label": "KDIGO 2024",
        "evidence_level": "high",
        "notes": ">90 = prawidłowa filtracja; interpretować z kreatyniną i nawodnieniem",
    },

    # ======================================================================
    # Stan zapalny
    # ======================================================================
    "crp__direct": {
        "label_pl": "CRP", "group": "zapalenie",
        "unit": "mg/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 1.0,
        "source_type": "GUIDELINE", "source_label": "AHA/CDC",
        "evidence_level": "high",
        "notes": "CRP <1.0 = niskie ryzyko CV; norma lab <5",
    },

    # ======================================================================
    # Minerały i elektrolity
    # ======================================================================
    "wapn__direct": {
        "label_pl": "Wapń całkowity", "group": "mineraly",
        "unit": "mmol/l", "expression_type": "direct",
        "optimal_low": 2.2, "optimal_high": 2.5,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "",
    },
    "fosfor__direct": {
        "label_pl": "Fosfor nieorganiczny", "group": "mineraly",
        "unit": "mmol/l", "expression_type": "direct",
        "optimal_low": 0.9, "optimal_high": 1.3,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "",
    },
    "magnez__direct": {
        "label_pl": "Magnez", "group": "mineraly",
        "unit": "mmol/l", "expression_type": "direct",
        "optimal_low": 0.85, "optimal_high": 1.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 0.66-1.07; suboptymalny mimo suplementacji",
    },
    "zelazo__direct": {
        "label_pl": "Żelazo", "group": "mineraly",
        "unit": "µg/dl", "expression_type": "direct",
        "optimal_low": 60.0, "optimal_high": 150.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "cynk__direct": {
        "label_pl": "Cynk", "group": "mineraly",
        "unit": "µg/dl", "expression_type": "direct",
        "optimal_low": 80.0, "optimal_high": 120.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "miedz__direct": {
        "label_pl": "Miedź", "group": "mineraly",
        "unit": "µg/dl", "expression_type": "direct",
        "optimal_low": 80.0, "optimal_high": 120.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "selen__direct": {
        "label_pl": "Selen", "group": "mineraly",
        "unit": "µg/l", "expression_type": "direct",
        "optimal_low": 100.0, "optimal_high": 140.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "sod__direct": {
        "label_pl": "Sód", "group": "mineraly",
        "unit": "mmol/l", "expression_type": "direct",
        "optimal_low": 138.0, "optimal_high": 142.0,
        "source_type": "LAB", "source_label": "Norma laboratoryjna",
        "evidence_level": "high",
        "notes": "",
    },
    "potas__direct": {
        "label_pl": "Potas", "group": "mineraly",
        "unit": "mmol/l", "expression_type": "direct",
        "optimal_low": 4.0, "optimal_high": 4.8,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },

    # ======================================================================
    # Witaminy
    # ======================================================================
    "witamina_d3__direct": {
        "label_pl": "Witamina D3 25(OH)", "group": "witaminy",
        "unit": "ng/ml", "expression_type": "direct",
        "optimal_low": 40.0, "optimal_high": 60.0,
        "source_type": "GUIDELINE", "source_label": "Endocrine Society 2024",
        "evidence_level": "high",
        "notes": "Suplementacja D3+K2 w profilu pacjenta",
    },

    # ======================================================================
    # Metale ciężkie
    # ======================================================================
    "arsen__direct": {
        "label_pl": "Arsen we krwi", "group": "metale",
        "unit": "µg/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 5.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "low",
        "notes": "Norma lab <10.7; cel prewencyjny <5",
    },
    "olow__direct": {
        "label_pl": "Ołów we krwi", "group": "metale",
        "unit": "µg/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 20.0,
        "source_type": "GUIDELINE", "source_label": "CDC",
        "evidence_level": "high",
        "notes": "CDC: brak bezpiecznego poziomu ołowiu; <20 µg/L = niskie narażenie",
    },
    "kadm__direct": {
        "label_pl": "Kadm we krwi", "group": "metale",
        "unit": "µg/l", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 0.3,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "low",
        "notes": "Norma lab <0.5; cel prewencyjny <0.3",
    },

    # ======================================================================
    # Kwasy tłuszczowe / Omega
    # ======================================================================
    "indeks_omega3__direct": {
        "label_pl": "Indeks Omega-3", "group": "kwasy_tluszczowe",
        "unit": "%", "expression_type": "direct",
        "optimal_low": 8.0, "optimal_high": None,
        "source_type": "GUIDELINE", "source_label": "Harris & von Schacky 2004",
        "evidence_level": "high",
        "notes": ">8% = najniższe ryzyko chorób sercowo-naczyniowych; 4-8% średnio korzystny; <4% niekorzystny",
    },
    "aa_epa__ratio": {
        "label_pl": "AA/EPA", "group": "kwasy_tluszczowe",
        "unit": "ratio", "expression_type": "ratio",
        "optimal_low": 1.5, "optimal_high": 3.0,
        "source_type": "GUIDELINE", "source_label": "Omega test guidelines",
        "evidence_level": "moderate",
        "notes": "1.5-3 = niski poziom stanu zapalnego; 3-6 = umiarkowany; >7 = podwyższony",
    },
    "omega6_omega3__ratio": {
        "label_pl": "Omega-6/Omega-3", "group": "kwasy_tluszczowe",
        "unit": "ratio", "expression_type": "ratio",
        "optimal_low": 3.5, "optimal_high": 5.5,
        "source_type": "GUIDELINE", "source_label": "Omega test guidelines",
        "evidence_level": "moderate",
        "notes": "3.5-5.5 = korzystny stosunek omega-6 do omega-3",
    },
    "indeks_tluszczow_trans__direct": {
        "label_pl": "Indeks tłuszczów trans", "group": "kwasy_tluszczowe",
        "unit": "%", "expression_type": "direct",
        "optimal_low": None, "optimal_high": 2.0,
        "source_type": "GUIDELINE", "source_label": "Omega test guidelines",
        "evidence_level": "moderate",
        "notes": "<2% = korzystny; 2-2.5% = średnio korzystny; >2.5% = niekorzystny",
    },
    "nkt_jnkt__ratio": {
        "label_pl": "NKT/JNKT", "group": "kwasy_tluszczowe",
        "unit": "ratio", "expression_type": "ratio",
        "optimal_low": 1.7, "optimal_high": 2.0,
        "source_type": "GUIDELINE", "source_label": "Omega test guidelines",
        "evidence_level": "moderate",
        "notes": "1.7-2.0 = najniższe ryzyko nagłej śmierci sercowej",
    },

    # ======================================================================
    # Morfologia
    # ======================================================================
    "erytrocyty__abs": {
        "label_pl": "Erytrocyty", "group": "morfologia",
        "unit": "mln/µl", "expression_type": "abs",
        "optimal_low": 4.5, "optimal_high": 5.5,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 4.6-6.5 (mężczyźni)",
    },
    "hemoglobina__direct": {
        "label_pl": "Hemoglobina", "group": "morfologia",
        "unit": "g/dl", "expression_type": "direct",
        "optimal_low": 14.0, "optimal_high": 16.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 13.5-18",
    },
    "hematokryt__pct": {
        "label_pl": "Hematokryt", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": 42.0, "optimal_high": 48.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 40-52%",
    },
    "leukocyty__abs": {
        "label_pl": "Leukocyty", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": 4.0, "optimal_high": 7.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 4-10; niskie leukocyty mogą być konstytucjonalne",
    },
    "neutrofile__abs": {
        "label_pl": "Neutrofile", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z Neutrofile %",
    },
    "neutrofile__pct": {
        "label_pl": "Neutrofile", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": 45.0, "optimal_high": 65.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 45-70%",
    },
    "limfocyty__abs": {
        "label_pl": "Limfocyty", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": 1.5, "optimal_high": 3.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "",
    },
    "limfocyty__pct": {
        "label_pl": "Limfocyty", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z Limfocyty abs",
    },
    "monocyty__abs": {
        "label_pl": "Monocyty", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z Monocyty %",
    },
    "monocyty__pct": {
        "label_pl": "Monocyty", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": 2.0, "optimal_high": 8.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 2-9%",
    },
    "eozynofile__abs": {
        "label_pl": "Eozynofile", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z Eozynofile %",
    },
    "eozynofile__pct": {
        "label_pl": "Eozynofile", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": 0.0, "optimal_high": 4.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 0-5%; optymalnie 0-4%",
    },
    "bazofile__abs": {
        "label_pl": "Bazofile", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "Interpretować łącznie z Bazofile %",
    },
    "bazofile__pct": {
        "label_pl": "Bazofile", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": 0.0, "optimal_high": 1.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 0-1.1%",
    },
    "plytki__abs": {
        "label_pl": "Płytki krwi", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "mpv__direct": {
        "label_pl": "MPV", "group": "morfologia",
        "unit": "fl", "expression_type": "direct",
        "optimal_low": 8.0, "optimal_high": 11.0,
        "source_type": "HEURISTIC", "source_label": "Medycyna prewencyjna",
        "evidence_level": "moderate",
        "notes": "Norma lab 7-12; duże płytki mogą wskazywać na aktywację",
    },
    "mcv__direct": {
        "label_pl": "MCV", "group": "morfologia",
        "unit": "fl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "mchc__direct": {
        "label_pl": "MCHC", "group": "morfologia",
        "unit": "g/dl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "rdw_sd__direct": {
        "label_pl": "RDW-SD", "group": "morfologia",
        "unit": "fl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "pdw__direct": {
        "label_pl": "PDW", "group": "morfologia",
        "unit": "fl", "expression_type": "direct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "p_lcr__pct": {
        "label_pl": "P-LCR", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "nrbc__abs": {
        "label_pl": "NRBC#", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "nrbc__pct": {
        "label_pl": "NRBC%", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "ig__abs": {
        "label_pl": "Niedojrzałe granulocyty IG il.", "group": "morfologia",
        "unit": "tys/µl", "expression_type": "abs",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
    "ig__pct": {
        "label_pl": "Niedojrzałe granulocyty IG %", "group": "morfologia",
        "unit": "%", "expression_type": "pct",
        "optimal_low": None, "optimal_high": None,
        "source_type": None, "source_label": "",
        "evidence_level": "",
        "notes": "",
    },
}


# ---------------------------------------------------------------------------
# Alias map:  (Parametr, unit_hint) → marker_id
#
# unit_hint is the unit extracted from the Wynik column.  For markers where
# the Parametr name alone is unambiguous, unit_hint can be "*" (wildcard).
#
# Lookup order:  exact (parametr, unit) → wildcard (parametr, "*")
# ---------------------------------------------------------------------------

# Units that signal absolute count vs percentage
_ABS_UNITS = {"tys/µl", "mln/µl"}
_PCT_UNITS = {"%"}

ALIAS_MAP: dict[tuple[str, str], str] = {
    # Lipidy
    ("Cholesterol całkowity", "*"):          "cholesterol_calkowity__direct",
    ("Cholesterol HDL", "*"):                "cholesterol_hdl__direct",
    ("Cholesterol LDL", "*"):                "cholesterol_ldl__direct",
    ("Cholesterol nie-HDL", "*"):            "cholesterol_nie_hdl__direct",
    ("Triglicerydy", "*"):                   "triglicerydy__direct",
    ("Apo B", "*"):                          "apo_b__direct",
    ("Homocysteina", "*"):                   "homocysteina__direct",
    ("D-dimer", "*"):                        "d_dimer__direct",
    ("CRP wysokiej czułości", "*"):          "hscrp__direct",

    # Węglowodany
    ("Glukoza", "*"):                        "glukoza__direct",
    ("Hemoglobina glikowana", "*"):          "hba1c__direct",

    # Hormony
    ("Testosteron", "*"):                    "testosteron__direct",
    ("Testosteron wolny", "*"):              "testosteron_wolny__direct",
    ("SHBG", "*"):                           "shbg__direct",
    ("LH", "*"):                             "lh__direct",
    ("FSH", "*"):                            "fsh__direct",
    ("Prolaktyna", "*"):                     "prolaktyna__direct",
    ("IGF-1", "*"):                          "igf1__direct",

    # Tarczyca
    ("TSH", "*"):                            "tsh__direct",
    ("FT4", "*"):                            "ft4__direct",

    # Prostata
    ("PSA", "*"):                            "psa__direct",
    ("PSA wolny", "*"):                      "psa_wolny__direct",
    ("PSA - wskaźnik (fPSA/PSA)", "*"):      "psa_wskaznik__ratio",

    # Wątroba
    ("ALT", "*"):                            "alt__direct",
    ("AST", "*"):                            "ast__direct",
    ("Bilirubina całkowita", "*"):           "bilirubina__direct",
    ("GGTP", "*"):                           "ggtp__direct",
    ("Fosfataza zasadowa", "*"):             "fosfataza_zasadowa__direct",

    # Nerki
    ("Kreatynina", "*"):                     "kreatynina__direct",
    ("eGFR", "*"):                           "egfr__calculated",

    # Stan zapalny
    ("CRP", "*"):                            "crp__direct",

    # Minerały
    ("Wapń całkowity", "*"):                 "wapn__direct",
    ("Fosfor nieorganiczny", "*"):           "fosfor__direct",
    ("Magnez", "*"):                         "magnez__direct",
    ("Żelazo", "*"):                         "zelazo__direct",
    ("Cynk", "*"):                           "cynk__direct",
    ("Miedź", "*"):                          "miedz__direct",
    ("Selen", "*"):                          "selen__direct",
    ("Sód", "*"):                            "sod__direct",
    ("Potas", "*"):                          "potas__direct",

    # Witaminy
    ("Witamina D3 metabolit 25(OH)", "*"):   "witamina_d3__direct",

    # Metale ciężkie
    ("Arsen we krwi", "*"):                  "arsen__direct",
    ("Ołów we krwi", "*"):                   "olow__direct",
    ("Kadm we krwi", "*"):                   "kadm__direct",

    # Morfologia — dual-expression markers (abs vs pct)
    ("Erytrocyty", "*"):                     "erytrocyty__abs",
    ("Hemoglobina", "*"):                    "hemoglobina__direct",
    ("Hematokryt", "*"):                     "hematokryt__pct",
    ("Leukocyty", "*"):                      "leukocyty__abs",
    ("Płytki krwi", "*"):                    "plytki__abs",
    ("MPV", "*"):                            "mpv__direct",
    ("MCV", "*"):                            "mcv__direct",
    ("MCHC", "*"):                           "mchc__direct",
    ("RDW-SD", "*"):                         "rdw_sd__direct",
    ("PDW", "*"):                            "pdw__direct",
    ("P-LCR", "*"):                          "p_lcr__pct",

    # Dual abs/pct — resolved by unit
    ("Neutrofile", "tys/µl"):                "neutrofile__abs",
    ("Neutrofile", "%"):                     "neutrofile__pct",
    ("Limfocyty", "tys/µl"):                "limfocyty__abs",
    ("Limfocyty", "%"):                      "limfocyty__pct",
    ("Monocyty", "tys/µl"):                 "monocyty__abs",
    ("Monocyty", "%"):                       "monocyty__pct",
    ("Eozynofile", "tys/µl"):               "eozynofile__abs",
    ("Eozynofile", "%"):                     "eozynofile__pct",
    ("Bazofile", "tys/µl"):                 "bazofile__abs",
    ("Bazofile", "%"):                       "bazofile__pct",
    ("NRBC#", "*"):                          "nrbc__abs",
    ("NRBC%", "*"):                          "nrbc__pct",
    ("Niedojrzałe granulocyty IG %", "*"):   "ig__pct",
    ("Niedojrzałe granulocyty IG il.", "*"): "ig__abs",

    # Kwasy tłuszczowe / Omega (PDF names)
    ("Indeks Omega-3", "*"):                  "indeks_omega3__direct",
    ("AA/EPA", "*"):                          "aa_epa__ratio",
    ("Omega 6/omega 3", "*"):                 "omega6_omega3__ratio",
    ("Indeks tłuszczów TRANS", "*"):          "indeks_tluszczow_trans__direct",
    ("NKT/JNKT", "*"):                        "nkt_jnkt__ratio",
}


def resolve_marker_id(parametr: str, unit: str) -> str | None:
    """Resolve a (Parametr, unit) pair to a canonical marker_id.

    Returns None if no alias matches — the caller should flag these as
    unmapped and include them in the data-quality section.
    """
    # Try exact match first
    key = (parametr, unit)
    if key in ALIAS_MAP:
        return ALIAS_MAP[key]
    # Fallback to wildcard
    key_wild = (parametr, "*")
    if key_wild in ALIAS_MAP:
        return ALIAS_MAP[key_wild]
    return None
