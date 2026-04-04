# Phase 6 Re-evaluation After Fixes

Data: 2026-04-04

## Findings

1. Medium: per-marker trend metadata still underreports observation count for threshold-heavy markers.

   The trend pipeline now computes both exact trend points and total observations, including threshold rows, in [generate_report.py](generate_report.py#L818-L823). However, the section renderer still displays only `n_measurements` in [generate_report.py](generate_report.py#L1861-L1861). As a result, the eGFR row in the generated report still says `n=1` in [raport_zdrowotny.html](raport_zdrowotny.html#L1422-L1425), even though the chart and source data clearly contain seven observations. The earlier recommendation bug is fixed, but the user-facing metadata remains misleading.

2. Low: stable trends now render with a duplicated arrow token.

   The template renders both the mathematical arrow and the clinical direction marker in the same span in [report_template.html](report_template.html#L333-L336). For stable trends, both values resolve to `→`, producing output like `→ +0.0% →` in many rows, for example eGFR in [raport_zdrowotny.html](raport_zdrowotny.html#L1422-L1425). This is only a presentation issue, but it makes stable rows look noisy.

## Verified Fixes

- The false `single measurement` retest recommendation for eGFR is fixed. eGFR no longer appears in the single-measurement retest block in [raport_zdrowotny.html](raport_zdrowotny.html#L3229-L3236).
- Contradictory trend arrows are fixed for worsening upward trends. LDL, TSH and Potas now render as mathematically consistent `↑ +... ✗` instead of `↓✗ +...`, visible in [raport_zdrowotny.html](raport_zdrowotny.html#L451-L454), [raport_zdrowotny.html](raport_zdrowotny.html#L1047-L1050) and [raport_zdrowotny.html](raport_zdrowotny.html#L1704-L1707).
- Morphology recommendations now disambiguate `abs` and `%` variants with units, visible in [raport_zdrowotny.html](raport_zdrowotny.html#L3011-L3018).
- The contradictory cholesterol reassurance is fixed. The report now correctly states that LDL and/or Apo B are above optimum in [raport_zdrowotny.html](raport_zdrowotny.html#L3033-L3040).

## Validation Performed

- Re-ran the generator end to end with `.venv/bin/python3 generate_report.py`.
- Re-checked the generated HTML at the previously broken locations.
- Re-read the updated recommendation and trend rendering code in [generate_report.py](generate_report.py) and [report_template.html](report_template.html).

## Summary

The four previously reported logic issues are fixed in substance. Two residual presentation issues remain: one medium-severity mismatch in reported observation count for markers like eGFR, and one low-severity formatting issue for stable trends.