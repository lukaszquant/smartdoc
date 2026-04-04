# Phase 3 — Marker Catalog & Status Assessment — Notes

## Marker catalog completion

All 69 markers in `marker_catalog.py` now include:
- `optimal_low`, `optimal_high` — optimal range boundaries (None = no bound)
- `source_type` — LAB, GUIDELINE, HEURISTIC, or None (no optimal defined)
- `source_label` — specific reference (e.g. "ESC/EAS 2021", "KDIGO 2024")
- `evidence_level` — "high", "moderate", "low"
- `notes` — contextual notes

### Source distribution

| Source type | Count | Examples |
|---|---|---|
| GUIDELINE | 12 | ESC/EAS 2021, KDIGO 2024, Endocrine Society 2024, AHA/CDC, CDC |
| HEURISTIC | 28 | Medycyna prewencyjna, Prati et al. 2002 |
| LAB | 7 | Norma laboratoryjna |
| None (no optimal) | 22 | Mostly auxiliary morfologia markers (abs/pct counterparts, MCV, MCHC, etc.) |

## assess_status() logic

Priority order:
1. **No data** → BRAK DANYCH
2. **Threshold values** (`<`/`>`) → best-effort inference; if threshold is clearly within/outside range, assess; otherwise WARTOŚĆ PROGOWA
3. **Outside lab range** → PONIŻEJ NORMY / POWYŻEJ NORMY (severity: high)
4. **Outside optimal range** → PONIŻEJ OPT / POWYŻEJ OPT (severity: moderate)
5. **Barely outside optimal** (within 1% of boundary) → GRANICA OPT (severity: low)
6. **Within optimal** → OK

Design choice: values inside the optimal range are always OK (no inside-range GRANICA detection). This avoids false positives for narrow ranges (e.g. Sód 138-142 where most values would trigger GRANICA).

## Validation against PLAN_ANALIZY.md Section 6

### WYMAGAJĄCE UWAGI (poza normą lab) — all 8 matched ✓
- Leukocyty 3.39 → PONIŻEJ NORMY
- Erytrocyty 4.43 → PONIŻEJ NORMY
- Neutrofile % 42.5 → PONIŻEJ NORMY
- Limfocyty abs 1.3 → PONIŻEJ NORMY
- Eozynofile % 9.4 → POWYŻEJ NORMY
- Bazofile % 1.5 → POWYŻEJ NORMY
- MPV 12.7 → POWYŻEJ NORMY
- SHBG 66.3 → POWYŻEJ NORMY

### POWYŻEJ OPTYMALNYCH — all 8 matched ✓
- HbA1c 5.7 → POWYŻEJ OPT
- Apo B 0.89 → POWYŻEJ OPT
- Homocysteina 12.8 → POWYŻEJ OPT
- TSH 2.47 → POWYŻEJ OPT
- LDL 105.6 → POWYŻEJ OPT
- eGFR 87.44 → PONIŻEJ OPT
- Magnez 0.81 → PONIŻEJ OPT
- Cynk 73 → PONIŻEJ OPT

### POZYTYWNE — all matched ✓
Triglicerydy, HDL, CRP/hsCRP, D-dimer, Witamina D3, PSA, ALT, AST, GGTP, Bilirubina — all OK.

### Known differences vs Section 4 tables

Three markers have lab_high < latest value, so our algorithm correctly flags them as POWYŻEJ NORMY instead of the plan's POWYŻEJ OPT/GRANICA OPT:
- **Cholesterol 191.8** (lab 115-190) → POWYŻEJ NORMY (plan: POWYŻEJ OPT)
- **Testosteron 894** (lab 249-836) → POWYŻEJ NORMY (plan: GRANICA OPT górna)
- **Monocyty % 9.1** (lab 2-9) → POWYŻEJ NORMY (plan: LEKKO POWYŻEJ)

These are improvements — the algorithm correctly identifies that these values exceed the laboratory reference range, which is clinically more important than the optimal range comparison.

One minor difference: **Glukoza 89** with optimal <90 is assessed as OK (value is within the <90 range) vs plan's GRANICA OPT. This is by design — values inside the optimal range are OK.

## Status distribution (69 markers)

| Status | Count |
|---|---|
| OK | 43 |
| POWYŻEJ OPT | 8 |
| POWYŻEJ NORMY | 7 |
| PONIŻEJ OPT | 5 |
| PONIŻEJ NORMY | 5 |
| GRANICA OPT | 1 (Selen) |
| **TOTAL** | **69** |
