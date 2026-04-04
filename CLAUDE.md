# Claude Code conventions for smartdoc

## Project overview

Reusable Python script (`generate_report.py`) that generates an interactive HTML health report in Polish from ~77 CSV blood test files and ~15 PDF files (2022-2026). Built in 6 phases:

1. **Data ingestion** — parse semicolon-delimited CSVs from `wynki_diag/` and PDFs from `wyniki_pdf/` (OCR via tesseract for Diagnostyka/Read-Gene, pdfplumber for Omega), normalize dates, handle comparators (`<`, `>`)
2. **Deduplication** — consolidate duplicate files (e.g. `(1)` suffixes), resolve conflicting values
3. **Marker catalog** — canonical `marker_id` mapping, optimal ranges (preventive medicine, not just lab norms), status assessment (OK / GRANICA OPT / POWYŻEJ OPT / POWYŻEJ NORMY / etc.)
4. **Trend analysis** — linear regression on time series, confidence levels, direction interpretation (clinical vs mathematical)
5. **Recommendations** — prioritized, Polish-language recs covering diet, supplementation, lifestyle, retesting
6. **HTML report** — Jinja2 template with Plotly interactive charts, trend summaries, color-coded status badges

## Key files

| File | Description |
|---|---|
| `generate_report.py` | Main script (~2180 lines) — all 6 phases |
| `pdf_parser.py` | PDF extraction layer — OCR (Diagnostyka, Read-Gene) + pdfplumber (Omega) |
| `marker_catalog.py` | `MARKERS` dict (canonical marker definitions, optimal ranges, units) and `GROUPS` |
| `report_template.html` | Jinja2 HTML template with Plotly chart rendering |
| `wynki_diag/` | Input CSV data (sensitive, gitignored) |
| `wyniki_pdf/` | Input PDF data (sensitive, gitignored) |
| `raport_zdrowotny.html` | Generated output (sensitive, gitignored) |
| `PLAN_ANALIZY.md` | Original project plan in Polish |
| `NOTES_PHASE*.md` | Implementation notes per phase |
| `REVIEW_*.md` | External review findings, responses, and fix plans |

## Tech stack

- Python 3.12, virtualenv at `.venv/`
- pandas, numpy, plotly 6.6, jinja2 3.1
- pdfplumber, PyMuPDF (fitz) — PDF parsing
- tesseract-ocr (system) — OCR for CID-encoded/image-only PDFs
- Report language: Polish

## Running the generator

```bash
.venv/bin/python3 generate_report.py
```

Output: `raport_zdrowotny.html`

## Running temporary test scripts

Use the **Write tool** to create throwaway scripts as `_tmp.py` (or `_tmp_check.py`, `_tmp_test.py`, etc.) in the project root, then run with:

```bash
.venv/bin/python3 _tmp.py 2>&1
```

Do NOT use `cat << 'PYEOF'`, `python3 << 'EOF'`, or any bash heredocs — use the Write tool to create the file, then run it. This keeps both steps auto-approved.

This ensures the correct virtualenv is used and both stdout and stderr are captured.

## Running one-off commands

Always use `_tmp*.py` for quick checks (dependency availability, data exploration, etc.) instead of running Python one-liners directly in the shell.

## Sensitive data

`wynki_diag/` (raw CSVs), `wyniki_pdf/` (PDF results), and `raport_zdrowotny.html` (generated report) contain personal health data. All are gitignored. Never commit these.

## Handling external reviews

When reacting to an external review of the implementation:

1. **First** — write a `REVIEW_RESPONSE_<phase>.md` file with analysis of each finding (agree/disagree, root cause, impact).
2. **Second** — write a `REVIEW_PLAN_<phase>.md` file with the concrete fix plan (what to change, where, in what order).
3. **Stop and present both files** to the user for approval before implementing any fixes.
