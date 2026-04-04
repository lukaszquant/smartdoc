# Review Response: PDF Ingestion Plan v2

## Finding 1 (Medium): `source_origin` lost during normalization

**Agree.** `normalize_records()` builds output dicts by hand and doesn't copy `source_origin`. It would be silently dropped.

**Resolution:** Add `source_origin` to the dict built in `normalize_records()` (line ~248-266), copying it from the input row. One line of code.

## Finding 2 (Medium): Overlap strategy overstated — dedup doesn't guarantee CSV preference

**Agree.** The current dedup uses `collected_at` sorting and `idxmax()` for ties, not source preference. Concat order doesn't actually matter.

**Resolution:** Add an explicit CSV-preference rule. In the same-day conflict resolution (Step 2 of dedup, ~line 331-340), when two rows have the same `marker_id` + `collected_date` and different `source_origin`, prefer `csv` over `pdf`. This is a minor tweak: before the existing `idxmax()` fallback, check if one row has `source_origin == "csv"` and keep it. This only affects true conflicts (same marker, same day, different values from CSV vs PDF); exact duplicates are already removed in Step 1.

## Finding 3 (Medium): Selenium and Arsenic already exist in catalog

**Agree.** Both markers already exist — the plan incorrectly listed them as "new entries."

**Resolution:**
- **Selen:** Keep in `mineraly` (where it is now). No group change. Just add ALIAS_MAP entry for the Read-Gene PDF name if it differs from the existing alias.
- **Arsen:** Already in `metale`. Same — just add alias if needed.
- **Olow, Kadm:** Also already in `metale`. Same treatment.
- No new marker definitions needed for these four. Only ALIAS_MAP entries for PDF name variants.

## Open Questions — Answers

1. **`source_origin` scope:** Yes, preserve it through normalization and consolidation. Useful for debugging overlap and for potential future "data source" annotations in the report.
2. **Overlap preference:** Explicit CSV preference for same-day conflicts. CSV is the established, validated source.
3. **Selenium group:** Keep in `mineraly`. No reclassification.
