# Phase 2 — Deduplication & Consolidation — Notes

## Dedup results

| Step | Records removed | Records after |
|---|---|---|
| Input (from Phase 1) | — | 602 |
| Exact duplicates | -58 | 544 |
| Same-day repeats | -12 | 532 |
| Same-day conflicts | -25 | 507 |

## Exact duplicates (58 removed)

All from `(1)` suffix file copies: identical `marker_id` + `collected_at` + `raw_value` + `source_order_id`.
Affected markers: TSH, Neutrofile%, NRBC%, IGF-1, Magnez, Apo B, Homocysteina (as predicted in Phase 1 notes).

## Same-day conflicts (25 resolved)

Three dates with multiple different-value measurements:

### 2023-07-04 — full morfologia + TSH + Wapń (17 conflicts + 11 same-day repeats)
Two separate blood draws minutes apart (different Kod zlecenia). 17 markers had slightly different values (flagged as conflicts), 11 had identical values (treated as repeats).
Conflict examples: TSH 2.09 vs 2.14, Erytrocyty 4.31 vs 4.20, MCV 91.6 vs 93.1.
→ Kept latest timestamp per marker.

### 2025-06-02 — lipid panel (5 conflicts)  
Two lipid panels: Cholesterol 170.3 vs 175.4, HDL 75.5 vs 73.9, LDL 85.96 vs 92.72, TG 40.9 vs 41.8, nie-HDL 94.8 vs 101.5.
→ Kept latest timestamp.

### 2026-03-20 — Magnez, TSH, Miedź (3 conflicts)
Magnez 0.78 vs 0.81, TSH 2.52 vs 2.47, Miedź 82.0 vs 88.3 (Miedź from different labs).
→ Kept latest timestamp.

## Count validation vs PLAN_ANALIZY.md Section 4

Plan counts included same-day duplicates (pre-dedup), so consolidated counts are slightly lower:
- Lipid panel: 10 (plan said 11) — 2025-06-02 same-day conflict merged
- TSH: 8 (plan said 9) — 2023-07-04 same-day conflict merged  
- FT4: 5 (plan said 6) — same-day repeat on one date
- CBC markers: 12 each (plan said 13) — 2023-07-04 merged

All latest values match plan's reference snapshot exactly.

## Quality flags summary

| Flag | Count |
|---|---|
| same_day_conflict | 25 |
| threshold_value | 12 |
| method_or_range_change | 7 |
| **Total flagged records** | **44** |

## Architecture

- `consolidate_measurements(df)` returns `(df, stats_dict)` — clean DataFrame + stats for reporting
- Same-day resolution is deterministic: always picks latest `collected_at`
- Conflict flag added to `quality_flags` column (semicolon-separated, append-only)
- All removed records are accounted for in stats — no silent data loss
