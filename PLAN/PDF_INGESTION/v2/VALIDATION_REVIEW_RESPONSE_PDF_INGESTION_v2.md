# Validation: Review Response for PDF Ingestion Plan v2

Reviewed response: [REVIEW_RESPONSE_PDF_INGESTION_v2.md](REVIEW_RESPONSE_PDF_INGESTION_v2.md)

Overall assessment: mostly accepted. The response cleanly resolves Findings 1 and 3. One medium issue remains in the proposed resolution for Finding 2.

## Findings

1. Medium: the proposed CSV-preference rule is too narrow.

The response says the new source-preference rule only needs to affect true same-day conflicts with different values, because exact duplicates are already removed in Step 1. That is not fully correct.

In the current dedup logic, Step 1 removes duplicates using `marker_id`, `collected_at`, `raw_value`, and `source_order_id`. See [generate_report.py](generate_report.py#L315-L319). A CSV row and a PDF row can therefore carry the same logical measurement and still survive Step 1 if their `source_order_id` values differ, which they usually will. Those rows then fall into the same-day grouping logic in Step 2. See [generate_report.py](generate_report.py#L321-L340). If their numeric values are identical, they are treated as same-day repeats rather than conflicts.

So the response should be amended as follows: CSV preference must apply to both same-day conflicts and same-day repeats when `source_origin` differs. An equivalent alternative would be to change Step 1 so cross-source duplicates can collapse before the repeat/conflict split.

## Accepted Responses

1. Preserve `source_origin` through normalization and consolidation. This closes the provenance-loss issue raised in the review.
2. Keep Selenium in `mineraly` and reuse existing `arsen__direct`, `olow__direct`, and `kadm__direct` marker definitions. Only alias additions are needed if the PDF strings differ.

## Recommended Amendment

For grouped same-day overlaps, the preference rule should be stated as:

1. If both CSV and PDF rows exist for the same `marker_id` and `collected_date`, select from CSV rows first.
2. Within the preferred source, keep the latest timestamp.
3. Apply the existing repeat/conflict bookkeeping after that choice so stats and flags remain accurate.

## Conclusion

The review response is directionally correct and nearly complete. It becomes implementation-ready once the overlap-preference rule is broadened from different-value conflicts to all same-day cross-source overlaps.