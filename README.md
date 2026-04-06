# SmartDoc

Polish-language interactive health report generator. Ingests blood test results from CSV and PDF files (2022-2026), consolidates ~100 biomarkers, runs trend analysis, and produces an HTML report with Plotly charts and prioritized recommendations.

## Features

- **Multi-source ingestion** — semicolon-delimited CSVs + PDFs (OCR via tesseract for Diagnostyka/Read-Gene, pdfplumber for Omega)
- **Marker catalog** — canonical mapping with optimal ranges (preventive medicine, not just lab norms), severity tiers (mild/severe deviation)
- **Robust trend analysis** — Theil-Sen slope, Mann-Kendall test, bootstrap CI, sufficiency gate, same-day collapse
- **Specialist consultation reports** — per-specialist routing with targeted marker subsets
- **Interactive HTML report** — Plotly charts, color-coded status badges, trend summaries
- **PDF export** — Playwright HTML-to-PDF conversion
- **PDF extraction cache** — per-file cache avoids redundant OCR on repeat runs

## Quick start

### Prerequisites

- Python 3.12+
- tesseract-ocr (system package, for OCR-based PDF parsing)

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install pandas numpy plotly jinja2 pdfplumber PyMuPDF
```

For PDF export (optional):

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

### Configuration

```bash
cp config.example.json config.json
```

Edit `config.json` to point to your data directories. Paths can be absolute or relative to the script directory.

```json
{
  "data_dir": "wynki_diag",
  "pdf_dir": "wyniki_pdf",
  "output_path": "raport_zdrowotny.html",
  "pdf_cache_dir": ".pdf_cache"
}
```

### Generate the report

```bash
.venv/bin/python3 generate_report.py
```

Output: `raport_zdrowotny.html`

### Run tests

```bash
.venv/bin/python3 -m pytest tests/ -q
```

## Project structure

```
generate_report.py          Main script — ingestion, dedup, status, trends, recs, HTML
marker_catalog.py           Canonical marker definitions, optimal ranges, groups
pdf_parser.py               PDF extraction (OCR + pdfplumber), per-file cache
report_template.html        Jinja2 HTML template with Plotly charts
report_specialist_template.html  Specialist consultation report template
config.example.json         Config template
tests/                      pytest suite (64 tests)
NOTES/                      Implementation notes by phase
PLAN/                       Feature plans and reviews
RELEASE_NOTES.md            Changelog
```

## How it works

1. **Ingestion** — parses CSVs and PDFs, normalizes dates, handles comparators (`<`, `>`)
2. **Deduplication** — consolidates duplicate files, resolves conflicting values
3. **Status assessment** — maps markers to canonical IDs, compares against lab and optimal ranges
4. **Trend analysis** — Theil-Sen + Mann-Kendall with sufficiency gate (n >= 5, span >= 180d, >= 4 unique dates, no unit/method change)
5. **Recommendations** — prioritized Polish-language guidance: diet, supplementation, lifestyle, retesting
6. **Report rendering** — Jinja2 template with interactive Plotly charts and color-coded badges

## Environment variables

| Variable | Effect |
|---|---|
| `SMARTDOC_NO_PDF_CACHE=1` | Disable PDF extraction cache for a run |

## License

Private project. Not licensed for redistribution.
