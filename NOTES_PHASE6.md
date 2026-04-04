# Phase 6 — HTML Report with Plotly Charts — Notes

## Implementation

### Files
- `generate_report.py` — Phase 6 section: `generate_plotly_chart()`, context builders, `render_html()`
- `report_template.html` — Jinja2 template (autoescape=True, charts marked `|safe`)
- `raport_zdrowotny.html` — generated output (~705 KB)

### Architecture

```
render_html()
├── _build_dashboard(status_df, trend_df) → summary stats
├── _build_group_sections(df, status_df, trend_df) → 12 group sections
│   └── generate_plotly_chart(df, marker_id, status_row) → per-marker Plotly div
├── _build_trends_summary(trend_df) → worsening/improving/stable lists
├── _build_recommendations_context(rec_df) → 5 categories with items
├── _build_quality_context(df) → data quality stats
└── Jinja2 template rendering → raport_zdrowotny.html
```

### Report structure

| Section | Content |
|---|---|
| Header | Report date, patient profile, data range |
| Nav | Sticky navigation bar with all section links |
| Dashboard | 6-7 summary cards (total, OK, suboptimal, borderline, out-of-lab, worsening, improving) |
| Per-group (×12) | Marker table (value, lab range, optimal, status badge, trend, date) + expandable Plotly charts |
| Trends | Worsening markers, improving markers, stable count |
| Recommendations | 5 categories, priority color-coded, medical escalation flag |
| Data quality | Record counts, quality flags, threshold markers |
| Methodology | Status legend, confidence criteria, consolidation rules |
| Disclaimer | Legal disclaimer (informational only, not a medical diagnosis) |

### Plotly charts

Per-marker interactive line charts:
- **Lab range bands**: light red zones outside lab range (above/below)
- **Optimal range band**: light green zone for optimal range
- **Boundary lines**: dashed red (lab), dotted green (optimal)
- **Data points**: blue connected lines for exact values, grey diamonds for threshold values
- **Hover**: date, value, unit
- Charts lazy-loaded via toggle ("wykres" link) with Plotly resize on open

### Template features
- Responsive CSS (640px breakpoint for mobile)
- Print-friendly (nav hidden, all charts forced open)
- Jinja2 autoescape enabled (XSS protection)
- Plotly CDN (v2.35.2) loaded once, individual charts use `include_plotlyjs=False`

## Results

- 70 Plotly chart divs (one per marker with numeric data)
- All 12 marker groups rendered with tables and charts
- 21 recommendations across 5 categories
- Dashboard: 69 markers, 43 OK (62%), 13 suboptimal, 1 borderline, 12 out-of-lab

## Review fixes applied

1. **Badge class precedence (M1)** — GRANICA OPT now checked before generic `'OPT' in status`, so it gets `badge-granica` (yellow) instead of `badge-opt` (orange).
2. **Borderline dashboard card (M3)** — Added conditional card for `borderline_count` (GRANICA OPT markers).
3. **Collected date display (M5)** — Last measurement date now shown in trend cell for all markers.
4. **Jinja2 autoescaping (M6)** — Switched from `Template()` to `Environment(autoescape=True)`. Chart HTML marked with `|safe` filter.
5. **Dead code cleanup (L1/L2)** — Removed unused `band_x0`/`band_x1` variables and no-op NaN loop.
6. **NaN guard (L3)** — `val_str` now checks `pd.notna(val)` in addition to `val is not None`.

### Deferred items
- **M2**: Dashboard sub-items (health score, flag list, top-5 priorities) — spec aspirational, current dashboard provides useful summary
- **M4**: Per-group commentary — would require a rule-based summary engine, out of scope for Phase 6
- **L4**: One-sided optimal range with no lab bound — edge case, charts still render correctly without green band
- **L5**: Plotly template bloat — standard behavior, 705 KB is acceptable
- **L6**: Detailed quality section (dedup stats, method-change breakdown) — current summary is sufficient
