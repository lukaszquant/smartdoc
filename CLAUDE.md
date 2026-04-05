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
| `config.json` | Local config for data paths (gitignored, see `config.example.json`) |
| `config.example.json` | Example config template with default relative paths |
| `pdf_parser.py` | PDF extraction layer — OCR (Diagnostyka, Read-Gene) + pdfplumber (Omega) |
| `marker_catalog.py` | `MARKERS` dict (canonical marker definitions, optimal ranges, units) and `GROUPS` |
| `report_template.html` | Jinja2 HTML template with Plotly chart rendering |
| `wynki_diag/` | Input CSV data (sensitive, gitignored) |
| `wyniki_pdf/` | Input PDF data (sensitive, gitignored) |
| `raport_zdrowotny.html` | Generated output (sensitive, gitignored) |
| `PLAN/` | Plans and reviews, organized by feature and version |
| `PLAN/ANALIZY/v1/` | Original project plan in Polish |
| `PLAN/PDF_INGESTION/` | PDF ingestion plans, reviews, validations (v1–v3) |
| `PLAN/SPECIALIST_RECS/` | Specialist recommendations plan and review |
| `NOTES/` | Implementation notes per phase (NOTES_PHASE1–6.md) |

## Tech stack

- Python 3.12, virtualenv at `.venv/`
- pandas, numpy, plotly 6.6, jinja2 3.1
- pdfplumber, PyMuPDF (fitz) — PDF parsing
- tesseract-ocr (system) — OCR for CID-encoded/image-only PDFs
- playwright (headless Chromium) — PDF export of generated HTML reports
  - Install: `.venv/bin/pip install playwright && .venv/bin/playwright install chromium`
- Report language: Polish

## Running the generator

```bash
.venv/bin/python3 generate_report.py
```

Output: `raport_zdrowotny.html`

### Configuration

Copy `config.example.json` to `config.json` and adjust paths. All paths can be absolute or relative to the script directory. If `config.json` is absent, defaults to `wynki_diag/` and `wyniki_pdf/` in the project root.

```json
{
  "data_dir": "/path/to/wynki_diag",
  "pdf_dir": "/path/to/wyniki_pdf",
  "output_path": "raport_zdrowotny.html"
}
```

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

## Planning new features

When planning a new feature or significant change:

1. **Create a plan file** in `PLAN/<FEATURE_NAME>/PLAN_v1.md` (increment version for revisions).
2. **Present the plan** to the user for approval before implementing.
3. Plans stay in `PLAN/` for reference — they are gitignored.

Do NOT put plans inline in the conversation. Always write them to a file.

## Handling external reviews

When reacting to an external review of the implementation:

1. **First** — write a `REVIEW_RESPONSE_<phase>.md` file with analysis of each finding (agree/disagree, root cause, impact).
2. **Second** — write a `REVIEW_PLAN_<phase>.md` file with the concrete fix plan (what to change, where, in what order).
3. **Stop and present both files** to the user for approval before implementing any fixes.
