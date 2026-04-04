# Phase 6 External Review — Fix Plan

## H1: eGFR single-measurement wording

**Where:** `generate_report.py` — `analyze_trends()` and retest rule in `generate_recommendations()`

**Plan:**
1. In `analyze_trends()`, count total observations (including thresholds) per marker_id before the threshold filter. Store as `total_observations` in the trend result dict.
2. In the retest rule (line ~1462), check `total_observations` instead of `n_measurements` when deciding "single measurement" wording.
3. eGFR (7 total obs) will no longer match `total_observations == 1`.

## H2: Trend arrows contradict delta_pct

**Where:** `generate_report.py` — `_DIRECTION_ARROWS` dict, `_build_group_sections()`, `_build_trends_summary()`, and `report_template.html` trend cells

**Plan:**
1. Change `_DIRECTION_ARROWS` to only show clinical assessment symbols (✓/✗/→), not directional arrows.
2. Add `_DIRECTION_COLORS` dict mapping clinical direction to colors (green=poprawa, red=pogorszenie, grey=neutral).
3. Add `math_arrow` field (↑/↓/→) derived from `delta_pct` sign — always matches the number.
4. In template: render as `math_arrow delta_pct direction_arrow` in the clinical color. E.g., "↑ +9.8% ✗" in red = value went up, that's bad.
5. Apply same pattern to trends summary section.

## M1: Disambiguate abs/pct morphology labels

**Where:** `generate_report.py` — `_label()` helper inside `generate_recommendations()`

**Plan:**
1. Modify `_label()` to check `expression_type` from marker catalog.
2. If expression_type is "abs" or "pct", append `[unit]` to the label (e.g., "Neutrofile [tys/µl]", "Neutrofile [%]").
3. This automatically disambiguates all abs/pct pairs in all recommendation text.

## M2: Guard cholesterol reassurance

**Where:** `generate_report.py` — cholesterol softening branch in medical recs (~line 1052-1066)

**Plan:**
1. Add `_status_of(mid)` helper to look up a marker's status from `status_df`.
2. Before emitting the "prawidłowym LDL i Apo B" reassurance, check that both `cholesterol_ldl__direct` and `apo_b__direct` have OK or GRANICA OPT status.
3. If both OK: emit existing reassurance + downgrade to low priority.
4. If either NOT OK: emit alternative text noting LDL/Apo B are above optimal, keep moderate priority, suggest evaluating lipid profile together.
