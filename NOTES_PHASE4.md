# Phase 4 — Trend Analysis — Notes

## Implementation

- Linear regression via `numpy.polyfit` (scipy not available in venv)
- R² computed manually from residuals
- Threshold values (`<`/`>`) excluded from trend analysis — their numeric values are bounds, not exact measurements
- Slope expressed as change per year (`slope_per_year`)
- Delta% = `(last - first) / |first| * 100`

## Direction interpretation

Direction (poprawa/pogorszenie/stabilny) is context-aware based on Phase 3 status:

| Current status | Rising trend | Falling trend |
|---|---|---|
| PONIŻEJ NORMY/OPT | poprawa | pogorszenie |
| POWYŻEJ NORMY/OPT | pogorszenie | poprawa |
| OK / GRANICA OPT | wzrost | spadek |
| (any, \|delta%\| < 5%) | stabilny | stabilny |

This avoids hard-coding per-marker "preferred direction" — the status already encodes which direction is needed.

## Confidence levels

| Level | Criteria |
|---|---|
| none | n < 2 (single measurement) |
| low | n = 2 |
| moderate | n ≥ 3 |
| high | n ≥ 5 AND R² ≥ 0.3 AND span ≥ 365 days |

## Results summary

### Confidence distribution (68 markers with non-threshold data)

| Confidence | Count |
|---|---|
| high | 15 |
| moderate | 38 |
| low | 1 (Testosteron wolny) |
| none | 14 (single measurement) |

### Direction distribution

| Direction | Count |
|---|---|
| stabilny | 33 |
| wzrost | 12 |
| spadek | 9 |
| pogorszenie | 11 |
| poprawa | 3 |

### Concerning trends (pogorszenie, moderate+ confidence)

| Marker | Δ% | Slope/yr | Confidence | Status |
|---|---|---|---|---|
| Leukocyty | -23.6% | -0.40 | high | PONIŻEJ NORMY |
| Limfocyty abs | -27.8% | -0.19 | high | PONIŻEJ NORMY |
| TSH | +27.3% | +0.19 | high | POWYŻEJ OPT |
| MPV | +10.4% | +0.32 | high | POWYŻEJ NORMY |
| Potas | +13.3% | +0.18 | high | POWYŻEJ OPT |
| Testosteron | +53.9% | +61.85 | high | POWYŻEJ NORMY |
| LDL | +9.8% | +1.79 | moderate | POWYŻEJ OPT |
| nie-HDL | +9.4% | +1.98 | moderate | POWYŻEJ OPT |
| Neutrofile abs | -21.3% | -0.13 | moderate | PONIŻEJ NORMY |
| Bazofile % | +200.0% | +0.05 | moderate | POWYŻEJ NORMY |
| Eozynofile % | +34.3% | -0.25 | moderate | POWYŻEJ NORMY |

### Improving trends

| Marker | Δ% | Confidence | Status |
|---|---|---|---|
| Erytrocyty | +5.5% | moderate | PONIŻEJ NORMY |
| Hematokryt | +6.1% | moderate | PONIŻEJ OPT |
| Monocyty % | -6.2% | moderate | POWYŻEJ NORMY |

## Validation against known patterns

### TSH rising trend ✓
1.94 → 2.47 over ~3.5 years, R²=0.65 (high confidence). Consistent upward drift, correctly flagged as pogorszenie given POWYŻEJ OPT status.

### Lipid trends ✓
- LDL rising +9.8%, cholesterol stable, HDL falling -9.1% — all consistent with a slight lipid profile deterioration
- Triglicerydy stable at excellent levels (37.2)

### CBC concerning pattern ✓
Leukocyty (-23.6%), Limfocyty abs (-27.8%), Neutrofile abs (-21.3%) — all declining with high/moderate confidence. Combined with already-below-lab-range values, this is the most concerning pattern in the dataset.

### Threshold exclusion working correctly ✓
- eGFR: 7 records but 6 are thresholds (`>60`, `>90`), only 1 exact → n=1 in trends
- D-dimer: 3 records, 2 thresholds → n=1
- CRP: 6 records, 3 thresholds → n=3 (exact: 2.1, 0.4, 0.7)

## Design notes

### Testosteron "pogorszenie"
Testosteron 581→894 (+53.9%) is flagged as pogorszenie because status is POWYŻEJ NORMY (above lab range 249-836). Algorithmically correct — the value is rising further above the reference range. Clinically, high testosterone at 42 is generally desirable, but the algorithm correctly notes it exceeds the lab range and is still rising. The recommendations engine (Phase 5) can add context.

### Slope/delta sign disagreement (6 markers)
Six markers have slope and delta with opposite signs (e.g. Eozynofile % delta +34.3% but slope -0.25/yr). This occurs when the first-to-last change differs from the regression trend direction, typically because the peak/trough was mid-series. Direction uses delta% as the simpler, more interpretable metric.

### Eozynofile % negative slope but positive delta
Eozynofile % shows delta +34.3% (7.0→9.4) but slope/yr is -0.25. This means the overall first-to-last change is up, but the linear regression detects a recent downward trend (the peak was earlier). Direction is based on delta%, not slope — this is the simpler and more interpretable metric for the report.

### hsCRP absent from trends
hsCRP has 1 consolidated record which is a threshold (`<0.40`). After threshold filtering, zero exact records remain, so it does not appear in trend_df. This is correct — 69 markers in status_df, 68 in trend_df.

## Review fixes applied

1. **Arrow symbols (M1)** — arrows now show actual delta direction (↑/↓) with quality symbol (✓/✗) appended. Previously `↓✗` was hardcoded for all pogorszenie, misleading for rising-and-worsening markers like TSH.
2. **Division by zero guard (M3)** — `delta_pct` now handles `first_val=0` with `last_val!=0` as ±100% instead of silently returning 0%.
3. **Stale numbers (L2)** — confidence distribution updated to match actual output (high:15, moderate:38).
