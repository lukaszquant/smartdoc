# Plan: Specialist Doctor & Additional Tests Recommendations

## Context

Medical recommendations currently say "Omówić z lekarzem" (discuss with doctor) generically. The user wants actionable guidance: **which specialist** to see and **what extra tests** to order before the visit, based on which marker groups are abnormal.

## Approach

Enrich existing medical recommendations with two new fields rather than creating a new category. This keeps specialist info tightly coupled with the abnormal findings that trigger it.

Use a **two-tier routing model**: marker-level overrides for heterogeneous groups (e.g. `lipidy` contains D-dimer, homocysteina, hsCRP alongside lipid markers), with group-level fallback for clinically homogeneous groups.

**Mixed-specialist rule**: when a single group contains abnormal markers routing to different specialists, emit **one recommendation per distinct specialist**, each listing only its own markers. This fits the existing flat one-row-per-rec shape without any structural changes.

**Deduplication rule**: when the dedicated CBC hematology escalation fires, suppress overlapping generic `morfologia` specialist recommendations for those same markers. Non-overlapping morphology abnormalities still generate their own standard specialist recs.

**Generic fallback rule**: any group absent from `GROUP_SPECIALIST` keeps the current generic wording (`Omówić z lekarzem`) with no specialist and no additional tests. Today this includes `mineraly`, `witaminy`, and `kwasy_tluszczowe`.

## Data model for additional tests

Each test is a dict with:
- `label_pl` (str) — display string, always present
- `marker_id` (str | None) — canonical ID if the marker exists in MARKERS today; used for exact filtering
- `filter_aliases` (list[str] | None) — exact-match aliases for normalized Polish test names; used when `marker_id` is absent but the test is a standard lab assay that may appear in the catalog

`filter_aliases` are not fuzzy substrings. They are a short list of exact candidate labels that may appear in `MARKERS.label_pl` now or in the future.

**Filtering logic** (in order):
1. If `marker_id` is set and exists in `tested_marker_ids` → filter out
2. Else if any normalized `filter_aliases` entry matches a normalized tested marker label exactly → filter out
3. Else → keep (the test is external: imaging, functional, or not yet catalogued)

Normalization rule: lowercase + trim + collapse repeated whitespace. No fuzzy matching and no substring matching.

## Changes

### 1. `marker_catalog.py` — add `MARKER_SPECIALIST` + `GROUP_SPECIALIST` (after `GROUPS`, ~line 53)

**`MARKER_SPECIALIST`** — marker-level overrides (heterogeneous groups):

```python
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
```

**`GROUP_SPECIALIST`** — group-level fallback:

```python
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
    # Any group omitted here keeps generic "Omówić z lekarzem"
    # with no specialist and no additional tests.
}
```

Notes:
- Only `zelazo__direct` uses `marker_id` (the only relevant ID that exists in the catalog today)
- All other standard lab tests use `filter_aliases` for normalized exact matching
- External tests (imaging, functional) have neither field and are always shown
- Any group omitted from `GROUP_SPECIALIST` keeps generic "Omówić z lekarzem" wording with no specialist or additional tests

### 2. `generate_report.py` — extend `_rec()` (line 952)

Add two optional params: `specialist_pl=""`, `additional_tests_pl=None` (list of label strings). Backward-compatible.

### 3. `generate_report.py` — add `_resolve_specialist_recs()` helper

```python
def _resolve_specialist_recs(
    group: str,
    markers: list[str],
    tested_marker_ids: set[str],
    tested_labels_norm: set[str],
) -> list[tuple[str, list[str], list[str]]]:
    """Return list of (specialist_pl, marker_subset, filtered_test_labels).
    
    One entry per distinct specialist. Splits markers in mixed-specialist groups.
    """
```

Returns a list of tuples. Each tuple becomes one `_rec()` call. For homogeneous groups this returns a single entry; for mixed groups it returns multiple.

**Filtering implementation**:
```python
def _norm_label(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _filter_tests(tests: list[dict], tested_ids: set[str], tested_labels_norm: set[str]) -> list[str]:
    result = []
    for t in tests:
        mid = t.get("marker_id")
        if mid and mid in tested_ids:
            continue
        aliases = t.get("filter_aliases") or []
        if any(_norm_label(alias) in tested_labels_norm for alias in aliases):
            continue
        result.append(t["label_pl"])
    return result
```

### 4. `generate_report.py` — medical block (lines 1035-1117)

Compute `cbc_bad` **before** the main per-group medical loop and use it to suppress overlapping generic morphology recs:

```python
cbc_bad = {...}
suppressed_generic_markers = set(cbc_bad) if len(cbc_bad) >= 2 else set()
```

Replace the single `recs.append(_rec(...))` call with a loop over `_resolve_specialist_recs()` results:

```python
markers = [m for m in markers if m not in suppressed_generic_markers]
if not markers:
    continue

spec_recs = _resolve_specialist_recs(group, markers, tested_ids, tested_labels_norm)
for specialist_pl, spec_markers, extra_tests in spec_recs:
    # build details, trend_note, nuance for spec_markers subset
    # ...
    text = (f"Konsultacja — {specialist_pl}: ..." if specialist_pl
            else f"Omówić z lekarzem wyniki spoza normy ...")
    recs.append(_rec(..., specialist_pl=specialist_pl, additional_tests_pl=extra_tests))
```

Then emit the dedicated CBC hematology rec with `specialist_pl="hematolog"` and filtered `GROUP_SPECIALIST["morfologia"]` tests. Because the overlapping generic markers were suppressed above, this avoids duplicate hematology output for the same CBC pattern.

### 5. `generate_report.py` — `_build_recommendations_context()` (line 1937)

Pass through `specialist` and `additional_tests` in the items dict. Empty list → block hidden in template.

### 6. `report_template.html` — template (lines 414-422)

After `rec-text`:
```html
{% if item.specialist %}
<div class="rec-specialist">Zalecany specjalista: {{ item.specialist }}</div>
{% endif %}
{% if item.additional_tests %}
<div class="rec-additional-tests">
  <strong>Dodatkowe badania przed wizytą:</strong>
  <ul>{% for test in item.additional_tests %}<li>{{ test }}</li>{% endfor %}</ul>
</div>
{% endif %}
```

### 7. `report_template.html` — CSS (after line 152)

Style `.rec-specialist` and `.rec-additional-tests`.

### 8. Import update

Line 28: add `MARKER_SPECIALIST, GROUP_SPECIALIST` to the import.

## Files modified

| File | Nature of change |
|---|---|
| `marker_catalog.py` | Add `MARKER_SPECIALIST` + `GROUP_SPECIALIST` (~110 new lines) |
| `generate_report.py` | Extend `_rec()`, add `_resolve_specialist_recs()` + `_filter_tests()`, modify medical block, update context builder |
| `report_template.html` | Add CSS + conditional specialist/tests rendering |

## Verification

```bash
.venv/bin/python3 generate_report.py
```
Open `raport_zdrowotny.html` → Rekomendacje section. Verify:
- **Isolated D-dimer abnormality** → routes to internista/angiolog, NOT kardiolog
- **LDL + Apo B abnormal** → routes to kardiolog with lipid-specific extra tests
- **Żelazo already tested** (marker_id `zelazo__direct` exists in catalog) → filtered from morfologia additional tests
- **Any unmapped group abnormal** (currently e.g. `mineraly`, `witaminy`, `kwasy_tluszczowe`) → no specialist or additional_tests shown, generic "Omówić z lekarzem"
- **Empty additional_tests after filtering** → block hidden entirely
- **CBC leukopenia pattern + generic morfologia abnormalities** → no duplicate hematolog rec for the same leukopenia marker set
- **Mixed group (e.g. lipidy with LDL + D-dimer both abnormal)** → two separate recs: kardiolog for LDL, internista / angiolog for D-dimer
