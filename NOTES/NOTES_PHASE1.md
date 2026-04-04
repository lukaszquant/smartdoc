# Phase 1 — Data Ingestion & Normalization — Notes

## Data profiling findings

- **77 CSV files**, semicolon-separated, UTF-8
- **69 unique markers** (Parametr + unit combinations)
- **602 total records** across date range 2022-06-27 → 2026-03-20
- Files with `(1)`/`(2)` suffixes are content duplicates (confirmed for TSH, Neutrofile%, NRBC%, Magnez, IGF-1)

## Edge cases handled

| Pattern | Example | Handling |
|---|---|---|
| Threshold values | `<0.3 mg/l`, `>60 ml/min/1,73m2` | Parsed into `comparator` + `numeric_value` |
| Empty reference range | eGFR, lipids, PSA ratio, metals, vitamins (13 markers) | `lab_low=None, lab_high=None` |
| Range format `< value` | `< 150` (triglicerydy old range) | Parsed as `(None, 150.0)` |
| Method/range changes in Opis | `Uwaga! Zmiana wartości referencyjnych` | `quality_flags: ["method_or_range_change"]` |
| Dual expression types | Eozynofile abs (tys/µl) vs % | Resolved by unit in alias map |
| Same-day multiple measurements | Magnez 2026-03-20: 0.78 vs 0.81 (different Kod zlecenia) | Both kept — Phase 2 conflict resolution |
| Comma in unit name | `ml/min/1,73m2` (eGFR) | Handled — comma only in unit, not in numeric value |
| eGFR threshold values | `>60` (older) vs exact `87.44` (latest) | Both parsed correctly |

## Counts needing dedup attention (Phase 2)

| Marker | Raw count | Expected unique | Cause |
|---|---|---|---|
| Neutrofile % | 26 | 13 | `(1)` file is exact copy |
| NRBC % | 26 | 13 | `(1)` file is exact copy |
| TSH | 20 | 10 | `(1)` file is exact copy |
| IGF-1 | 16 | 8 | `(1)` file is exact copy |
| Magnez | 16 | 8 | `(1)` file is exact copy |
| Apo B | 10 | 5 | `(1)` file is exact copy |
| Homocysteina | 2 | 1 | `(1)` file is exact copy |
| Miedź | 2 | 1+1 | Two different labs same day (82 vs 88.3) = conflict |

## Validation against plan (Section 4)

All latest values match the plan's reference snapshot:
- ✓ Cholesterol 191.8, HDL 78.7, LDL 105.6, TG 37.2
- ✓ HbA1c 5.7%, Glukoza 89
- ✓ Testosteron 894, SHBG 66.3, Testosteron wolny 32.8
- ✓ TSH 2.47, FT4 1.19
- ✓ PSA 0.469, fPSA/PSA 35.39
- ✓ ALT 16, AST 23, GGTP 10
- ✓ eGFR 87.44, Kreatynina 1.09
- ✓ Leukocyty 3.39, Erytrocyty 4.43, MPV 12.7
- ✓ Eozynofile % 9.4, Neutrofile % 42.5, Bazofile % 1.5
- ✓ Magnez 0.81, Cynk 73, Witamina D3 46.1

## Architecture decisions

- `marker_id` = `canonical_name__expression_type` (double underscore separator)
- Alias map: `(Parametr, unit)` → `marker_id` with `"*"` wildcard for unambiguous markers
- All data kept as-is in raw layer; normalization adds computed columns without dropping originals
- Quality flags are lists (can accumulate multiple flags per record)
