# Review: PDF Ingestion Plan v2

Plan reviewed: [PLAN_PDF_INGESTION_v2.md](PLAN_PDF_INGESTION_v2.md)

Overall assessment: v2 fixes the major blockers from the first review. The schema mismatch is addressed, `source_type` is no longer overloaded, the file counts are corrected, and the plan now explicitly accounts for the Read-Gene zinc/copper specimen mismatch. I do not see any remaining high-severity issues, but there are still a few implementation gaps that should be corrected before work starts.

## Findings

1. Medium: `source_origin` is introduced at raw-ingestion time, but the plan does not carry it through normalization, so provenance will still be lost before deduplication and reporting.

The revised plan adds `source_origin` to the canonicalized PDF rows and to CSV rows in `load_raw_data()`. See [PLAN_PDF_INGESTION_v2.md](PLAN_PDF_INGESTION_v2.md#L71-L115). That is an improvement, but the current `normalize_records()` function only preserves `source_file`, `source_order_id`, `source_badanie`, and `source_notes` from the raw input. It does not copy any `source_origin` field into the normalized DataFrame. See [generate_report.py](generate_report.py#L214-L281), especially [generate_report.py](generate_report.py#L248-L266). As a result, once Phase 1 finishes, there is no longer any way to tell whether a surviving normalized record came from CSV or PDF.

This matters because the plan explicitly wants provenance symmetry and overlap analysis. If `source_origin` is meant to be usable beyond raw ingestion, the plan needs one more explicit change: preserve it in `normalize_records()` and keep it available through consolidation.

2. Medium: the overlap strategy is still described as if concat order determines tie resolution, but the current deduplication code does not guarantee that.

The revised plan says `CSV/PDF overlap: CSV rows appear first in concat; existing dedup resolves ties.` See [PLAN_PDF_INGESTION_v2.md](PLAN_PDF_INGESTION_v2.md#L198-L206). The current code does not implement a source-preference rule. After normalization, records are sorted only by `collected_at`. See [generate_report.py](generate_report.py#L269-L272). Dedup step 1 removes exact duplicates using `marker_id`, `collected_at`, `raw_value`, and `source_order_id`, which means a CSV row and a PDF row with the same measurement can survive step 1 if their order IDs differ. See [generate_report.py](generate_report.py#L315-L319). Step 2 then keeps the row with the latest timestamp, and for identical timestamps it falls back to `idxmax()` on the timestamp column, not on source preference. See [generate_report.py](generate_report.py#L331-L340).

So the plan’s current wording overstates what the existing dedupe gives you. If deterministic CSV-preferred or PDF-preferred behavior is desired for same-day overlap, the plan should say so explicitly and include a rule for it.

3. Medium: Step 5 still treats Selenium and Arsenic as new catalog entries, but those marker IDs already exist, and Selenium currently belongs to a different group.

The plan lists `selen__direct` and `arsen__direct` under `Metals — new entries`. See [PLAN_PDF_INGESTION_v2.md](PLAN_PDF_INGESTION_v2.md#L136-L142). In the current catalog, both already exist. `selen__direct` is already defined with unit `µg/l`, but it is grouped under `mineraly`, not `metale`. See [marker_catalog.py](marker_catalog.py#L397-L403). `arsen__direct` already exists under `metale`. See [marker_catalog.py](marker_catalog.py#L437-L444).

That means the plan cannot be implemented literally by “adding” those marker IDs. For arsenic, this is mostly wording drift. For selenium, it is a real behavioral question: changing `selen__direct` from `mineraly` to `metale` would move the full historical selenium series to a new report section. The plan should explicitly decide whether selenium stays in `mineraly`, moves to `metale`, or gets some other treatment.

## Open Questions

1. Is `source_origin` intended only for raw-ingest diagnostics, or should it survive into the normalized and consolidated dataset for later reporting and debugging?
2. For overlapping CSV/PDF rows with the same timestamp, do you want an explicit source-preference rule, or is non-deterministic retention acceptable?
3. Should Selenium remain in [marker_catalog.py](marker_catalog.py#L397) under `mineraly`, or do you want this project to reclassify it under `metale` going forward?

## Summary

v2 resolves the structural problems from the first plan review. The remaining work is mainly about tightening semantics: preserve provenance past normalization, make overlap resolution policy explicit if provenance matters, and clarify whether Selenium is being reused or reclassified.